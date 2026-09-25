def is_admin(event) -> bool:
    """Admin from Cognito JWT (through API Gateway Authorizer)."""
    claims = (event.get("requestContext", {})
                    .get("authorizer", {})
                    .get("claims", {})) or {}
    groups = claims.get("cognito:groups", "")
    return "Admin" in groups
