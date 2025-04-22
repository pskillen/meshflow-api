from django.contrib import admin

from .models import Constellation, ConstellationUserMembership, NodeAPIKey, NodeAuth

admin.site.register(Constellation)
admin.site.register(ConstellationUserMembership)
admin.site.register(NodeAPIKey)
admin.site.register(NodeAuth)
