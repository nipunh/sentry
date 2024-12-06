# Generated by Django 3.2.23 on 2024-01-24 17:07

from django.db import migrations

from sentry.new_migrations.migrations import CheckedMigration


class Migration(CheckedMigration):
    # This flag is used to mark that a migration shouldn't be automatically run in production. For
    # the most part, this should only be used for operations where it's safe to run the migration
    # after your code has deployed. So this should not be used for most operations that alter the
    # schema of a table.
    # Here are some things that make sense to mark as post deployment:
    # - Large data migrations. Typically we want these to be run manually by ops so that they can
    #   be monitored and not block the deploy for a long period of time while they run.
    # - Adding indexes to large tables. Since this can take a long time, we'd generally prefer to
    #   have ops run this and not block the deploy. Note that while adding an index is a schema
    #   change, it's completely safe to run the operation after the code has deployed.
    is_post_deployment = False

    allow_run_sql = True

    dependencies = [
        ("sentry", "0636_monitor_incident_env_resolving_index"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    hints={"tables": ["sentry_pullrequest_comment"]},
                    sql="ALTER TABLE IF EXISTS sentry_pullrequest_comment DROP CONSTRAINT IF EXISTS sentry_pullrequest_comment_pull_request_id_key",
                    reverse_sql="",
                ),
            ]
        ),
    ]
