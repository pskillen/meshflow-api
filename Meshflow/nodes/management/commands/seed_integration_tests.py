"""
Management command to seed the database with test data for integration tests.

Creates:
- A test User (integration-test@example.com)
- A Constellation
- A ManagedNode (observer, node_id=999999999)
- A NodeAPIKey with fixed key for reproducibility
- NodeAuth linking the key to the ManagedNode

The integration tests use the fixed API key for packet ingest and JWT for assertions.
"""

import os

from django.core.management.base import BaseCommand

from constellations.models import Constellation, ConstellationUserMembership, MessageChannel
from nodes.models import ManagedNode, NodeAPIKey, NodeAuth
from users.models import User

# Fixed values for reproducibility in CI and local runs
INTEGRATION_TEST_USERNAME = "integration-test@example.com"
INTEGRATION_TEST_PASSWORD = "integration-test-password"
INTEGRATION_TEST_NODE_ID = 999999999
INTEGRATION_TEST_NODE_ID_2 = 999999998  # Second observer for dedup tests
INTEGRATION_TEST_API_KEY = "integration-test-key-a1b2c3d4e5f6"


class Command(BaseCommand):
    help = "Seed database with integration test fixtures (User, Constellation, ManagedNode, NodeAPIKey, NodeAuth)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-env",
            action="store_true",
            help="Write MESHFLOW_NODE_API_KEY to a file for the test runner",
        )

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=INTEGRATION_TEST_USERNAME,
            defaults={
                "email": INTEGRATION_TEST_USERNAME,
                "is_active": True,
            },
        )
        if created:
            user.set_password(INTEGRATION_TEST_PASSWORD)
            user.save()
            self.stdout.write(f"Created user {INTEGRATION_TEST_USERNAME}")
        else:
            self.stdout.write(f"User {INTEGRATION_TEST_USERNAME} already exists")

        constellation, c_created = Constellation.objects.get_or_create(
            name="Integration Test Constellation",
            defaults={
                "description": "Constellation for integration tests",
                "created_by": user,
            },
        )
        if c_created:
            ConstellationUserMembership.objects.create(
                user=user,
                constellation=constellation,
                role="admin",
            )
            self.stdout.write("Created constellation")
        else:
            constellation.created_by = user
            constellation.save()

        # Ensure MessageChannels exist for ManagedNode
        ch0, _ = MessageChannel.objects.get_or_create(
            name="Channel 0",
            constellation=constellation,
            defaults={},
        )
        ch1, _ = MessageChannel.objects.get_or_create(
            name="Channel 1",
            constellation=constellation,
            defaults={},
        )

        managed_node, mn_created = ManagedNode.objects.get_or_create(
            node_id=INTEGRATION_TEST_NODE_ID,
            defaults={
                "owner": user,
                "constellation": constellation,
                "name": "Integration Test Observer",
                "channel_0": ch0,
                "channel_1": ch1,
                "allow_auto_traceroute": True,
            },
        )
        if mn_created:
            self.stdout.write(f"Created ManagedNode (node_id={INTEGRATION_TEST_NODE_ID})")
        else:
            managed_node.owner = user
            managed_node.constellation = constellation
            managed_node.allow_auto_traceroute = True
            managed_node.save()

        managed_node_2, mn2_created = ManagedNode.objects.get_or_create(
            node_id=INTEGRATION_TEST_NODE_ID_2,
            defaults={
                "owner": user,
                "constellation": constellation,
                "name": "Integration Test Observer 2",
                "channel_0": ch0,
                "channel_1": ch1,
                "allow_auto_traceroute": True,
            },
        )
        if mn2_created:
            self.stdout.write(f"Created ManagedNode 2 (node_id={INTEGRATION_TEST_NODE_ID_2})")
        else:
            managed_node_2.owner = user
            managed_node_2.constellation = constellation
            managed_node_2.allow_auto_traceroute = True
            managed_node_2.save()

        api_key, ak_created = NodeAPIKey.objects.update_or_create(
            key=INTEGRATION_TEST_API_KEY,
            defaults={
                "name": "Integration Test API Key",
                "constellation": constellation,
                "owner": user,
                "is_active": True,
            },
        )
        if ak_created:
            self.stdout.write("Created NodeAPIKey")
        else:
            self.stdout.write("Updated NodeAPIKey")

        NodeAuth.objects.get_or_create(
            api_key=api_key,
            node=managed_node,
        )
        NodeAuth.objects.get_or_create(
            api_key=api_key,
            node=managed_node_2,
        )
        self.stdout.write("NodeAuth links ensured")

        if options.get("output_env"):
            env_file = os.environ.get("INTEGRATION_ENV_FILE", "/tmp/integration_test_env")
            with open(env_file, "w") as f:
                f.write(f"MESHFLOW_NODE_API_KEY={INTEGRATION_TEST_API_KEY}\n")
                f.write(f"MESHFLOW_TEST_USERNAME={INTEGRATION_TEST_USERNAME}\n")
                f.write(f"MESHFLOW_TEST_PASSWORD={INTEGRATION_TEST_PASSWORD}\n")
            self.stdout.write(f"Wrote credentials to {env_file}")

        self.stdout.write(self.style.SUCCESS("Integration test seed complete"))
