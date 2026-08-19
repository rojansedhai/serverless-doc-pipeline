// Backend Configuration — populate from `terraform output` after deployment.
// See README.md for setup instructions.
const DEFAULT_CONFIG = {
  apiEndpoint: "YOUR_API_GATEWAY_ENDPOINT",       // e.g. https://abc123.execute-api.us-east-1.amazonaws.com
  cognitoUserPoolId: "YOUR_COGNITO_USER_POOL_ID", // e.g. us-east-1_XXXXXXXXX
  cognitoClientId: "YOUR_COGNITO_CLIENT_ID",       // e.g. 26-char alphanumeric string
  awsRegion: "us-east-1",
  s3BucketName: "YOUR_S3_BUCKET_NAME",             // e.g. doc-pipeline-storage-prod-xxxxxxxx
  dynamoDbTableName: "YOUR_DYNAMODB_TABLE_NAME",   // e.g. doc-pipeline-metadata-prod
  
  // Pre-configured Test Tenants (passwords must match Cognito user setup)
  tenants: {
    "tenant-alpha": {
      name: "Tenant Alpha (Enterprise)",
      badge: "Enterprise Tier",
      email: "tenant-alpha-admin@example.com",
      password: "YOUR_TENANT_ALPHA_PASSWORD",
      theme: "indigo"
    },
    "tenant-beta": {
      name: "Tenant Beta (Logistics)",
      badge: "Standard Tier",
      email: "tenant-beta-admin@example.com",
      password: "YOUR_TENANT_BETA_PASSWORD",
      theme: "cyan"
    }
  }
};

export function getConfig() {
  const saved = localStorage.getItem("DOC_PIPELINE_CONFIG");
  if (saved) {
    try {
      return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
    } catch (e) {
      console.warn("Error parsing saved config:", e);
    }
  }
  return DEFAULT_CONFIG;
}

export function saveConfig(newConfig) {
  localStorage.setItem("DOC_PIPELINE_CONFIG", JSON.stringify(newConfig));
}
