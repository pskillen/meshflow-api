from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

class MergeByEmailSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # If user is already logged in, do nothing
        if request.user.is_authenticated:
            return

        # Try to find an existing user with the same email address

        active_email = sociallogin.user.email
        emails = sociallogin.email_addresses
        email_verified = False
        for email in emails:
            if email.email == active_email:
                email_verified = email.verified
                break

        if email and email_verified:
            User = get_user_model()
            try:
                user = User.objects.get(email=email)
                # If found, connect this new social account to the existing user
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass  # No user with this email, normal flow continues 