from django.db import migrations

FEEDER_GROUP_NAME = "feeder"


def create_feeder_group_and_grant_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("users", "User")
    group, _ = Group.objects.get_or_create(name=FEEDER_GROUP_NAME)

    user_ids = set()
    Membership = apps.get_model("constellations", "ConstellationUserMembership")
    ManagedNode = apps.get_model("nodes", "ManagedNode")

    for user_id in Membership.objects.filter(role__in=["admin", "editor"]).values_list("user_id", flat=True):
        user_ids.add(user_id)
    for owner_id in ManagedNode.objects.filter(deleted_at__isnull=True).exclude(owner_id__isnull=True).values_list(
        "owner_id", flat=True
    ):
        user_ids.add(owner_id)

    for user in User.objects.filter(id__in=user_ids):
        user.groups.add(group)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_discord_notify_fields"),
        ("constellations", "0010_meshcore_message_channel_proxy"),
        ("nodes", "0048_observednode_meshcore_adv_type"),
    ]

    operations = [
        migrations.RunPython(create_feeder_group_and_grant_roles, noop_reverse),
    ]
