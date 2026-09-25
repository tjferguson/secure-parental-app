export const config = {
  apiUrl: import.meta.env.VITE_API_URL || '',
  cognitoUserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
  cognitoClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
  cognitoRegion: import.meta.env.VITE_AWS_REGION || 'us-east-1',
  localDev: import.meta.env.VITE_LOCAL_DEV === 'true',
};
