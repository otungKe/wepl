from ._common import *  # shared imports/helpers (ADR-0013)


class UserProfileView(APIView):
    permission_classes = [IsActiveSession]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    def patch(self, request):
        """Update name, bio, and/or profile_photo."""
        serializer = UserSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


# -----------------------------
# 7. KYC
# -----------------------------
