import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django_zero_downtime_migrations.backends.postgres.schema import UnsafeOperationException

from sentry.testutils.cases import TestCase


def one_line_sql(sql: str) -> str:
    return (
        sql.replace("    ", "")
        .replace("\n", " ")
        .replace("( ", "(")
        .replace(" )", ")")
        .replace("  ", " ")
        .strip()
    )


def split_sql_queries(sql: str) -> list[str]:
    return [
        line
        for line in [one_line_sql(line) for line in sql.splitlines()]
        if line and not line.startswith("--")
    ]


class BaseSafeMigrationTest(TestCase):
    BASE_PATH = "fixtures.safe_migrations_apps"
    # abstract
    app: str
    migrate_from: str
    migrate_to: str

    def run_migration(self):
        self._run_migration(self.app, self.migrate_from)
        self._run_migration(self.app, self.migrate_to)

    def _run_migration(self, app, migration):
        with override_settings(
            INSTALLED_APPS=(f"{self.BASE_PATH}.{self.app}",), MIGRATION_MODULES={}
        ):
            executor = MigrationExecutor(connection)
            executor.loader.build_graph()
            target = [(app, migration)]
            executor.loader.project_state(target).apps
            executor.migrate(target)

    def sql_migrate(self, app_label, migration_name):
        with override_settings(
            INSTALLED_APPS=(f"{self.BASE_PATH}.{self.app}",), MIGRATION_MODULES={}
        ):
            target = (app_label, migration_name)
            executor = MigrationExecutor(connection)
            plan = [(executor.loader.graph.nodes[target], None)]
            sql_statements = executor.loader.collect_sql(plan)  # type: ignore[attr-defined]
            return "\n".join(sql_statements)


class AddColWithDefaultTest(BaseSafeMigrationTest):
    app = "bad_flow_add_column_with_default_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_add_field_default"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Adding TestTable.field as column with a default is safe, but you need to take additional steps.",
        ):
            self.run_migration()


class AddColWithNotNullDefaultTest(BaseSafeMigrationTest):
    app = "bad_flow_add_column_with_notnull_default_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_add_field_notnull_default"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Adding TestTable.field as column with a default is safe, but you need to take additional steps.",
        ):
            self.run_migration()


class AddColWithNotNullTest(BaseSafeMigrationTest):
    app = "bad_flow_add_column_with_notnull_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_add_field_notnull"

    def test(self):
        with pytest.raises(
            UnsafeOperationException, match="Adding TestTable.field as a not null column is unsafe."
        ):
            self.run_migration()


class ChangeCharTypeUnsafeTest(BaseSafeMigrationTest):
    app = "bad_flow_change_char_type_that_unsafe_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_change_type_from_char120_to_char100"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Altering the type of column TestTable.field in this way is unsafe",
        ):
            self.run_migration()


class ChangeDecimalToFloatTest(BaseSafeMigrationTest):
    app = "decimal_to_float_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_type_conversion"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Altering the type of column Value.amount in this way is unsafe",
        ):
            self.run_migration()


class RenameTableTest(BaseSafeMigrationTest):
    app = "bad_flow_rename_table_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_rename_table"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Renaming table for model NewTable from bad_flow_rename_table_app_testtable to bad_flow_rename_table_app_newtable is unsafe",
        ):
            self.run_migration()


class RenameFieldTest(BaseSafeMigrationTest):
    app = "bad_flow_rename_field_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_rename_field"

    def test(self):
        with pytest.raises(
            UnsafeOperationException, match="Renaming column TestTable.field to new_field is unsafe"
        ):
            self.run_migration()


class DeleteModelTest(BaseSafeMigrationTest):
    app = "bad_flow_delete_model_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_delete_model"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Deleting the TestTable model is unsafe.",
        ):
            self.run_migration()


class RemoveFieldTest(BaseSafeMigrationTest):
    app = "bad_flow_remove_field_app"
    migrate_from = "0001_initial"
    migrate_to = "0002_remove_field"

    def test(self):
        with pytest.raises(
            UnsafeOperationException,
            match="Removing the TestTable.field field is unsafe",
        ):
            self.run_migration()


class DeleteModelCorrectTest(BaseSafeMigrationTest):
    app = "good_flow_delete_model_state_app"
    migrate_from = "0001_initial"
    migrate_to = "0003_delete_table"

    def test(self):
        self.run_migration()


class LockTimeoutTest(BaseSafeMigrationTest):
    app = "run_sql_app"

    def test(self):
        with override_settings(
            ZERO_DOWNTIME_MIGRATIONS_LOCK_TIMEOUT="5s",
            ZERO_DOWNTIME_MIGRATIONS_STATEMENT_TIMEOUT="5s",
            ZERO_DOWNTIME_MIGRATIONS_LOCK_TIMEOUT_FORCE=True,
        ):
            migration_sql = self.sql_migrate(self.app, "0001_initial")
            # We'd never block while attempting to acquire a lock when creating a table, but since we set
            # `ZERO_DOWNTIME_MIGRATIONS_LOCK_TIMEOUT_FORCE` we should add a lock_timeout here anyway
            assert split_sql_queries(migration_sql) == [
                "SET lock_timeout TO '5s';",
                'CREATE TABLE "run_sql_app_testtable" ("id" integer NOT NULL PRIMARY KEY '
                'GENERATED BY DEFAULT AS IDENTITY, "field" integer NULL);',
                "SET lock_timeout TO '0ms';",
            ]
            self._run_migration(self.app, "0001_initial")
            migration_sql = self.sql_migrate(self.app, "0002_run_sql")
            # The runsql operation should just have the lock timeout set, since it's relying on
            # `ZERO_DOWNTIME_MIGRATIONS_LOCK_TIMEOUT_FORCE`
            assert split_sql_queries(migration_sql) == [
                "SET lock_timeout TO '5s';",
                'ALTER TABLE "run_sql_app_testtable" DROP COLUMN "field";',
                "SET lock_timeout TO '0ms';",
            ]
            self._run_migration(self.app, "0002_run_sql")
            migration_sql = self.sql_migrate(self.app, "0003_add_col")
            # This should set the statement timeout since it's an operation that dzdm handles
            assert split_sql_queries(migration_sql) == [
                "SET statement_timeout TO '5s';",
                "SET lock_timeout TO '5s';",
                'ALTER TABLE "run_sql_app_testtable" ADD COLUMN "field" integer NULL;',
                "SET statement_timeout TO '0ms';",
                "SET lock_timeout TO '0ms';",
            ]
