from ._common import *  # shared imports/helpers (ADR-0013 view split)
from ..lifecycle import AccountCannotClose, close_account


class AccountDeletionView(APIView):
    """
    DELETE /api/users/account/

    Kenya Data Protection Act 2019, Section 26: right to erasure of personal data.
    Financial records (ledger, transactions) are retained as required by CBK, and
    identity evidence for the anti-money-laundering retention period.

    ``apps.users.lifecycle.close_account`` does the work: every context may block
    the closure (an open advance, money held in a group, a community still
    relying on this creator) and then erases its own data, in one transaction.
    """
    permission_classes = [IsActiveSession]

    def delete(self, request):
        try:
            close_account(request.user, request=request)
        except AccountCannotClose as exc:
            return Response({'error': exc.reasons[0], 'reasons': exc.reasons},
                            status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)
