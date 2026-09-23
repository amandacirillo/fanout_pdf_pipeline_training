import { Stack, StackProps, Duration, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwIntegrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { EnvironmentConfig } from './environment';

export interface FanoutPipelineStackProps extends StackProps {
  envConfig: EnvironmentConfig;
}

/**
 * A minimal version of the real fan-out/fan-in stack: one queue that carries
 * both "request" and "worker" message types, one Lambda that handles both
 * SQS events and HTTP requests (see app/lambda_handler.py), an output
 * bucket, and an alert queue.
 */
export class FanoutPipelineStack extends Stack {
  constructor(scope: Construct, id: string, props: FanoutPipelineStackProps) {
    super(scope, id, props);

    const { envConfig } = props;

    const outputBucket = new s3.Bucket(this, 'OutputBucket', {
      bucketName: `fanout-pdf-pipeline-${envConfig.name}`,
      removalPolicy: envConfig.name === 'prd' ? RemovalPolicy.RETAIN : RemovalPolicy.DESTROY,
      autoDeleteObjects: envConfig.name !== 'prd',
    });

    const deadLetterQueue = new sqs.Queue(this, 'DeadLetterQueue', {
      queueName: `fanout-pdf-pipeline-${envConfig.name}-dlq`,
      retentionPeriod: Duration.days(14),
    });

    const requestQueue = new sqs.Queue(this, 'RequestQueue', {
      queueName: `fanout-pdf-pipeline-${envConfig.name}-queue`,
      visibilityTimeout: Duration.minutes(15),
      deadLetterQueue: { queue: deadLetterQueue, maxReceiveCount: 3 },
    });

    const alertQueue = new sqs.Queue(this, 'AlertQueue', {
      queueName: envConfig.alertQueueName,
    });

    const appFunction = new lambda.DockerImageFunction(this, 'AppFunction', {
      functionName: `fanout-pdf-pipeline-${envConfig.name}-app`,
      code: lambda.DockerImageCode.fromImageAsset('../../', { file: 'Dockerfile.lambda' }),
      // The dispatcher waits (poll-and-combine) inside a single invocation,
      // so this timeout has to comfortably exceed the slowest expected
      // worker run -- a direct cost of the "poll S3 for completion" design
      // discussed in the README.
      timeout: Duration.minutes(15),
      memorySize: 1024,
      environment: {
        BUCKET: outputBucket.bucketName,
        QUEUE_NAME: requestQueue.queueName,
        ALERT_QUEUE_NAME: alertQueue.queueName,
        ITEMS_PER_WORKER: String(envConfig.itemsPerWorker),
      },
    });

    outputBucket.grantReadWrite(appFunction);
    requestQueue.grantSendMessages(appFunction);
    requestQueue.grantConsumeMessages(appFunction);
    alertQueue.grantSendMessages(appFunction);

    appFunction.addEventSource(new lambdaEventSources.SqsEventSource(requestQueue, {
      batchSize: 1, // handlers.sqs_handler asserts it only ever receives one record at a time
    }));

    const httpApi = new apigw.HttpApi(this, 'HttpApi', {
      apiName: `fanout-pdf-pipeline-${envConfig.name}`,
    });
    httpApi.addRoutes({
      path: '/{proxy+}',
      integration: new apigwIntegrations.HttpLambdaIntegration('AppIntegration', appFunction),
    });
  }
}
