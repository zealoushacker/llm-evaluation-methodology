# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""CDK stack for AWS workshop on Large Language Model Evaluation"""
# Python Built-Ins:
from typing import Optional

# External Dependencies:
from aws_cdk import Stack, CfnParameter, CfnOutput
from constructs import Construct
from aws_cdk import aws_ec2, aws_iam

# Local Dependencies:
from .prompt_app import PromptEngineeringApp
from .smstudio import WorkshopSageMakerEnvironment


class LLMEvalWkshpStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        deploy_prompt_app: bool = True,
        deploy_sagemaker_domain: bool = True,
        sagemaker_code_checkout: Optional[str] = None,
        sagemaker_code_repo: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bedrock_role = aws_iam.Role(
            self,
            "BedrockRole",
            assumed_by=aws_iam.CompositePrincipal(
                aws_iam.ServicePrincipal("bedrock.amazonaws.com"),
                # SageMaker also needed for manual evaluation jobs. See:
                # https://docs.aws.amazon.com/bedrock/latest/userguide/model-eval--service-roles.html
                # https://docs.aws.amazon.com/bedrock/latest/userguide/automatic-service-roles.html
                aws_iam.ServicePrincipal("sagemaker.amazonaws.com"),
            ),
            description=(
                "Bedrock Execution Role for LLM Evaluation workshop, with access to S3 buckets "
                "SageMaker default and workshop prompt app data bucket."
            ),
            # Explicitly name the role so it's easier to find in console:
            role_name="Amazon-Bedrock-LLMEvalWorkshop",
            managed_policies=[
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
            ],
            inline_policies={
                "LLMEvaluation": aws_iam.PolicyDocument(
                    statements=[
                        aws_iam.PolicyStatement(
                            sid="S3Access",
                            effect=aws_iam.Effect.ALLOW,
                            actions=[
                                "s3:AbortMultipartUpload",
                                "s3:GetObject",
                                "s3:GetBucketLocation",
                                "s3:ListBucket",
                                "s3:ListBucketMultipartUploads",
                                "s3:PutObject",
                            ],
                            resources=[
                                f"arn:{self.partition}:s3:::sagemaker-{self.region}-{self.account}",
                                f"arn:{self.partition}:s3:::sagemaker-{self.region}-{self.account}/*",
                            ],
                            conditions={"StringEquals": {"aws:ResourceAccount": self.account}},
                        ),
                        aws_iam.PolicyStatement(
                            sid="ManageA2IHumanLoops",
                            effect=aws_iam.Effect.ALLOW,
                            actions=[
                                "sagemaker:DeleteHumanLoop",
                                "sagemaker:DescribeFlowDefinition",
                                "sagemaker:DescribeHumanLoop",
                                "sagemaker:StartHumanLoop",
                                "sagemaker:StopHumanLoop",
                            ],
                            resources=["*"],
                        ),
                    ],
                ),
            },
        )

        if deploy_sagemaker_domain:
            # Shared VPC:
            vpc = aws_ec2.Vpc(self, "Vpc")

            # Deploy SageMaker Studio environment:
            sagemaker_env = WorkshopSageMakerEnvironment(
                self,
                "SageMakerEnvironment",
                vpc=vpc,
                code_checkout=sagemaker_code_checkout,
                code_repo=sagemaker_code_repo,
                create_nbi=False,  # Don't create a 'Notebook Instance' (save costs, use Studio)
                domain_name="FMEvalWorkshopDomain",
                instance_type="ml.t3.large",
                studio_classic=False,  # Keep SMStudio classic disabled (save costs)
            )

        if deploy_prompt_app:
            cognito_username_param = CfnParameter(
                self,
                "PromptAppUsername",
                default="workshop",
                type="String",
            )
            cognito_password_param = CfnParameter(
                self,
                "PromptAppPassword",
                default="Time2Evalu8!",
                no_echo=True,
                type="String",
            )
            prompt_app = PromptEngineeringApp(
                self,
                "PromptEngineeringApp",
                cognito_demo_username=cognito_username_param.value_as_string,
                cognito_demo_password=cognito_password_param.value_as_string,
            )
            prompt_app.data_bucket.grant_read_write(bedrock_role)
            domain_name_output = CfnOutput(
                self,
                "AppDomainName",
                value=prompt_app.domain_name,
            )
            cognito_username_output = CfnOutput(
                self,
                "AppDemoUsername",
                value=prompt_app.demo_cognito_user.username,
            )
            # TODO: In a production environment you probably won't want to publish your pw:
            cognito_password_output = CfnOutput(
                self,
                "AppDemoPassword",
                value=prompt_app.demo_cognito_user.password,
            )
            data_bucket_output = CfnOutput(
                self,
                "DataBucket",
                value=prompt_app.data_bucket.bucket_name,
            )

        if deploy_prompt_app and deploy_sagemaker_domain:
            prompt_app.data_bucket.grant_read_write(sagemaker_env.execution_role)
