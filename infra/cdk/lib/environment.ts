/**
 * Resolves per-environment configuration from a short environment name.
 *
 * The real deploy pipeline determines this name from a parsed git tag (see
 * the README's "Tag-driven deploys" section) rather than a hardcoded map
 * like this training example uses -- but the shape of "one small config
 * object per environment, looked up by name" is the reusable part.
 */
export interface EnvironmentConfig {
  name: string;
  account: string;
  region: string;
  itemsPerWorker: number;
  alertQueueName: string;
}

const ENVIRONMENTS: Record<string, EnvironmentConfig> = {
  dev: {
    name: 'dev',
    account: '111111111111',
    region: 'us-east-1',
    itemsPerWorker: 25,
    alertQueueName: 'alerts-dev-queue',
  },
  stg: {
    name: 'stg',
    account: '222222222222',
    region: 'us-east-1',
    itemsPerWorker: 25,
    alertQueueName: 'alerts-stg-queue',
  },
  prd: {
    name: 'prd',
    account: '333333333333',
    region: 'us-east-1',
    itemsPerWorker: 50,
    alertQueueName: 'alerts-prd-queue',
  },
};

export function resolveEnvironment(name: string): EnvironmentConfig {
  const config = ENVIRONMENTS[name];
  if (!config) {
    throw new Error(`Unknown environment '${name}'. Valid options: ${Object.keys(ENVIRONMENTS).join(', ')}`);
  }
  return config;
}
