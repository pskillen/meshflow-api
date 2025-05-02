from rest_framework.routers import DefaultRouter
from .views import TextMessageViewSet

router = DefaultRouter()
router.register(r'text-messages', TextMessageViewSet, basename='textmessage')

urlpatterns = router.urls 