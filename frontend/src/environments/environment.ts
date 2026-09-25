
export const environment = {
  production: false,
  // API Gateway invoke URL printed by `serverless deploy`
  apiBase: 'https://<api-id>.execute-api.eu-central-1.amazonaws.com/dev',
  cognito: {
    userPoolId: '<USER_POOL_ID>',
    clientId:   '<APP_CLIENT_ID>',
    region:     'eu-central-1'
  }
};
