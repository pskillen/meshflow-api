"""Management command to export completed traceroutes to Neo4j."""

from django.core.management.base import BaseCommand, CommandError

from traceroute_analytics.neo4j_service import clear_all_routed_to_edges, export_all_traceroutes_to_neo4j


class Command(BaseCommand):
    help = "Export all completed AutoTraceRoute records to Neo4j (synchronous)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--async",
            action="store_true",
            dest="async_mode",
            help="Queue the export as a Celery task instead of running synchronously.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Delete every ROUTED_TO relationship before exporting. "
                "Useful when re-running a full backfill; requires the sync path."
            ),
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive confirmation prompt for --clear.",
        )

    def handle(self, *args, **options):
        clear = options.get("clear")
        async_mode = options.get("async_mode")

        if clear and async_mode:
            raise CommandError(
                "--clear cannot be combined with --async; the destructive delete must "
                "run synchronously so an operator can confirm it."
            )

        if clear:
            if not options.get("yes"):
                self.stdout.write(
                    self.style.WARNING("About to DELETE every ROUTED_TO relationship in Neo4j before re-export.")
                )
                answer = input("Type 'yes' to continue: ")
                if answer.strip().lower() != "yes":
                    self.stdout.write(self.style.NOTICE("Aborted; no changes made."))
                    return
            deleted = clear_all_routed_to_edges()
            self.stdout.write(self.style.SUCCESS(f"Cleared {deleted} ROUTED_TO relationships."))

        if async_mode:
            from traceroute.tasks import export_traceroutes_to_neo4j

            result = export_traceroutes_to_neo4j.delay()
            self.stdout.write(self.style.SUCCESS(f"Queued export task: {result.id}"))
        else:
            result = export_all_traceroutes_to_neo4j()
            self.stdout.write(
                self.style.SUCCESS(f"Exported {result['exported']} of {result['total']} traceroutes to Neo4j.")
            )
