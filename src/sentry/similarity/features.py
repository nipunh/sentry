import itertools
import logging

logger = logging.getLogger("sentry.similarity")


def get_application_chunks(exception):
    """\
    Filters out system and framework frames from a stacktrace in order to
    better align similar logical application paths. This returns a sequence of
    application code "chunks": blocks of contiguously called application code.
    """
    return [
        list(frames)
        for in_app, frames in itertools.groupby(
            exception.stacktrace.frames, key=lambda frame: frame.in_app
        )
        if in_app
    ]


class InterfaceDoesNotExist(KeyError):
    pass


class ExceptionFeature:
    def __init__(self, function):
        self.function = function

    def extract(self, event):
        try:
            interface = event.interfaces["exception"]
        except KeyError:
            raise InterfaceDoesNotExist()
        return self.function(interface.values[0])


class MessageFeature:
    def __init__(self, function):
        self.function = function

    def extract(self, event):
        try:
            interface = event.interfaces["logentry"]
        except KeyError:
            raise InterfaceDoesNotExist()
        return self.function(interface)


class FeatureSet:
    def __init__(
        self,
        index,
        encoder,
        aliases,
        features,
        expected_extraction_errors,
        expected_encoding_errors,
    ):
        self.index = index
        self.encoder = encoder
        self.aliases = aliases
        self.features = features
        self.expected_extraction_errors = expected_extraction_errors
        self.expected_encoding_errors = expected_encoding_errors
        assert set(self.aliases) == set(self.features)

    def __get_scope(self, project) -> str:
        return f"{project.id}"

    def __get_key(self, group) -> str:
        return f"{group.id}"

    def extract(self, event):
        results = {}
        for label, strategy in self.features.items():
            try:
                results[label] = strategy.extract(event)
            except Exception as error:
                log = (
                    logger.debug
                    if isinstance(error, self.expected_extraction_errors)
                    else logger.warning
                )
                log(
                    "Could not extract features from %r for %r due to error: %r",
                    event,
                    label,
                    error,
                    exc_info=True,
                )
        return results

    def record(self, events):
        if not events:
            return []

        scope: str | None = None
        key: str | None = None

        items = []
        for event in events:
            if not event.group_id:
                continue
            for label, features in self.extract(event).items():
                if scope is None:
                    scope = self.__get_scope(event.project)
                else:
                    assert (
                        self.__get_scope(event.project) == scope
                    ), "all events must be associated with the same project"

                if key is None:
                    key = self.__get_key(event.group)
                else:
                    assert (
                        self.__get_key(event.group) == key
                    ), "all events must be associated with the same group"

                try:
                    features = [self.encoder.dumps(feature) for feature in features]
                except Exception as error:
                    log = (
                        logger.debug
                        if isinstance(error, self.expected_encoding_errors)
                        else logger.warning
                    )
                    log(
                        "Could not encode features from %r for %r due to error: %r",
                        event,
                        label,
                        error,
                        exc_info=True,
                    )
                else:
                    if features:
                        items.append((self.aliases[label], features))

        return self.index.record(scope, key, items, timestamp=int(event.datetime.timestamp()))

    def classify(self, events, limit=None, thresholds=None):
        if not events:
            return []

        if thresholds is None:
            thresholds = {}

        scope: str | None = None

        labels = []
        items = []
        for event in events:
            for label, features in self.extract(event).items():
                if scope is None:
                    scope = self.__get_scope(event.project)
                else:
                    assert (
                        self.__get_scope(event.project) == scope
                    ), "all events must be associated with the same project"

                try:
                    features = [self.encoder.dumps(feature) for feature in features]
                except Exception as error:
                    log = (
                        logger.debug
                        if isinstance(error, self.expected_encoding_errors)
                        else logger.warning
                    )
                    log(
                        "Could not encode features from %r for %r due to error: %r",
                        event,
                        label,
                        error,
                        exc_info=True,
                    )
                else:
                    if features:
                        items.append((self.aliases[label], thresholds.get(label, 0), features))
                        labels.append(label)

        return [
            (int(key), dict(zip(labels, scores)))
            for key, scores in self.index.classify(
                scope,
                items,
                limit=limit,
                timestamp=int(event.datetime.timestamp()),
            )
        ]

    def compare(self, group, limit=None, thresholds=None):
        if thresholds is None:
            thresholds = {}

        features = list(self.features.keys())

        items = [(self.aliases[label], thresholds.get(label, 0)) for label in features]

        return [
            (int(key), dict(zip(features, scores)))
            for key, scores in self.index.compare(
                self.__get_scope(group.project), self.__get_key(group), items, limit=limit
            )
        ]

    def merge(self, destination, sources, allow_unsafe=False):
        def add_index_aliases_to_key(key):
            return [(self.aliases[label], key) for label in self.features.keys()]

        # Collect all of the sources by the scope that they are contained
        # within so that we can make the most efficient queries possible and
        # reject queries that cross scopes if we haven't explicitly allowed
        # unsafe actions.
        scopes: dict[str, set[str]] = {}
        for source in sources:
            scopes.setdefault(self.__get_scope(source.project), set()).add(source)

        unsafe_scopes = set(scopes.keys()) - {self.__get_scope(destination.project)}
        if unsafe_scopes and not allow_unsafe:
            raise ValueError(
                "all groups must belong to same project if unsafe merges are not allowed"
            )

        destination_scope = self.__get_scope(destination.project)
        destination_key = self.__get_key(destination)

        for source_scope, sources in scopes.items():
            items = []
            for source in sources:
                items.extend(add_index_aliases_to_key(self.__get_key(source)))

            if source_scope != destination_scope:
                imports = [
                    (alias, destination_key, data)
                    for (alias, _), data in zip(items, self.index.export(source_scope, items))
                ]
                self.index.delete(source_scope, items)
                self.index.import_(destination_scope, imports)
            else:
                self.index.merge(destination_scope, destination_key, items)

    def delete(self, group):
        key = self.__get_key(group)
        return self.index.delete(
            self.__get_scope(group.project),
            [(self.aliases[label], key) for label in self.features.keys()],
        )

    def flush(self, project):
        return self.index.flush(self.__get_scope(project), list(self.aliases.values()))
