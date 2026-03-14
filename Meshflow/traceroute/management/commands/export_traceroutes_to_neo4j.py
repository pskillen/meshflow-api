"""Management command to export completed traceroutes to Neo4j."""

from django.core.management.base import BaseCommand

from traceroute.neo4j_service import export_all_traceroutes_to_neo4j


class Command(BaseCommand):
    help = "Export all completed AutoTraceRoute records to Neo4j (synchronous)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--async",
            action="store_true",
            dest="async_mode",
            help="Queue the export as a Celery task instead of running synchronously.",
        )

    def handle(self, *args, **options):
        if options.get("async_mode"):
            from traceroute.tasks import export_traceroutes_to_neo4j

            result = export_traceroutes_to_neo4j.delay()
            self.stdout.write(
                self.style.SUCCESS(f"Queued export task: {result.id}")
            )
        else:
            result = export_all_traceroutes_to_neo4j()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exported {result['exported']} of {result['total']} traceroutes to Neo4j."
                )
            )
