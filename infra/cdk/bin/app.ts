import { App } from 'aws-cdk-lib';
import { FanoutPipelineStack } from '../lib/stack';
import { resolveEnvironment } from '../lib/environment';

const app = new App();

// The environment (dev/stg/prd) is resolved from a deploy-time tag/branch
// name, not hardcoded here -- see lib/environment.ts and the repo README's
// "Tag-driven deploys" section for how CI parses that out.
const env = resolveEnvironment(process.env.DEPLOY_ENV_NAME ?? 'dev');

new FanoutPipelineStack(app, `FanoutPdfPipeline-${env.name}`, {
  env: { region: env.region, account: env.account },
  envConfig: env,
});
