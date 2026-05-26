from rest_framework.permissions import BasePermission

class IsOTPRecovery(BasePermission):
    """
    Allows access only to revocery-stage JWT tokens.
    """

    def has_permission(self, request, view):

        if not request.auth:
            return False

        return request.auth.payload.get("stage") == "otp_recovery"
    
class IsOTPVerfied(BasePermission):
    """
    Allows access only to OTP-verified JWT tokens.
    """

    def has_permission(self, request, view):

        if not request.auth:
            return False

        return request.auth.payload.get("stage") == "otp_verified"
    