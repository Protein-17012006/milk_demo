/**
 * Public client configuration for Project A Shelf Analytics (Platform B — ap-southeast-1).
 * Note: Cognito UserPoolId, ClientId, and API Gateway URL are non-secret public identifiers.
 * Override per environment via Amplify Hosting environment variables.
 */
export const AWS_CONFIG = {
  region: process.env.NEXT_PUBLIC_AWS_REGION || "ap-southeast-1",
  apiBaseUrl: (
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "https://qq20q6drmi.execute-api.ap-southeast-1.amazonaws.com/v1"
  ).replace(/\/+$/, ""),
  cognitoUserPoolId:
    process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID || "ap-southeast-1_6MvmrWNmd",
  cognitoClientId:
    process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID || "60l85r4c624741f2mr9hecr81d",
} as const;
