from .models import Activity


class ActivityService:
    @staticmethod
    def log_activity(user, activity_type, message):
        return Activity.objects.create(
            user=user,
            activity_type=activity_type,
            message=message
        )