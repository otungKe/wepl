from django.conf import settings
from django.db import models

from apps.communities.models import Community


class Conversation(models.Model):
    """A named sub-channel within a community (topic-based chat)."""

    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='conversations'
    )

    topic = models.CharField(max_length=255)

    photo = models.ImageField(
        upload_to='conversations/',
        null=True,
        blank=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_conversations'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.community.name}] {self.topic}"


class Message(models.Model):
    MESSAGE_TYPES = (
        ('text', 'Text'),
        ('image', 'Image'),
        ('voice', 'Voice'),
        ('system', 'System'),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )

    reply_to = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='replies',
    )

    content = models.TextField(blank=True, default='')

    attachment = models.FileField(
        upload_to='messages/',
        null=True,
        blank=True,
    )

    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPES,
        default='text'
    )

    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at'], name='msg_conv_date_idx'),
            models.Index(fields=['conversation', 'is_deleted'],  name='msg_conv_deleted_idx'),
        ]

    def __str__(self):
        return f"{self.sender.phone_number}: {self.content[:30]}"


class MessageReaction(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='reactions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_reactions',
    )
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')

    def __str__(self):
        return f"{self.user.phone_number} {self.emoji} → {self.message_id}"


class ConversationReadStatus(models.Model):
    """Tracks the last time a user read a conversation."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversation_read_statuses'
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='read_statuses'
    )
    last_read_at = models.DateTimeField()
    # High-water-mark (ADR-0012): id of the last message the user has read.
    # Exact + cheap for unread counts vs. comparing timestamps row-by-row.
    last_read_message_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'conversation')
        indexes = [
            models.Index(fields=['conversation', 'user'], name='conv_read_conv_user_idx'),
        ]

    def __str__(self):
        return f"{self.user.phone_number} read {self.conversation_id} at {self.last_read_at}"
