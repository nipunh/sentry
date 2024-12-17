import inspect
from collections.abc import Callable, Iterator, Sequence
from typing import Any, Generic, Protocol, TypeVar, overload

from sentry import projectoptions
from sentry.eventstore.models import Event
from sentry.grouping.component import (
    BaseGroupingComponent,
    ExceptionGroupingComponent,
    FrameGroupingComponent,
    StacktraceGroupingComponent,
)
from sentry.grouping.enhancer import Enhancements
from sentry.interfaces.base import Interface
from sentry.interfaces.exception import SingleException
from sentry.interfaces.stacktrace import Frame, Stacktrace

STRATEGIES: dict[str, "Strategy[Any]"] = {}

RISK_LEVEL_LOW = 0
RISK_LEVEL_MEDIUM = 1
RISK_LEVEL_HIGH = 2

Risk = int  # TODO: make enum or union of literals

# XXX: Want to make ContextDict typeddict but also want to type/overload dict
# API on GroupingContext
ContextValue = Any
ContextDict = dict[str, ContextValue]

DEFAULT_GROUPING_ENHANCEMENTS_BASE = "common:2019-03-23"
DEFAULT_GROUPING_FINGERPRINTING_BASES: list[str] = []

# TODO: Hack to make `ReturnedVariants` (no pun intended) covariant. At some point we should
# probably turn `ReturnedVariants` into a Mapping (immutable), since in practice it's read-only.
GroupingComponent = TypeVar("GroupingComponent", bound=BaseGroupingComponent[Any])
ReturnedVariants = dict[str, GroupingComponent]
ConcreteInterface = TypeVar("ConcreteInterface", bound=Interface, contravariant=True)


class StrategyFunc(Protocol[ConcreteInterface]):
    def __call__(
        self,
        interface: ConcreteInterface,
        event: Event,
        context: "GroupingContext",
        **meta: Any,
    ) -> ReturnedVariants: ...


class VariantProcessor(Protocol):
    def __call__(
        self, variants: ReturnedVariants, context: "GroupingContext", **meta: Any
    ) -> ReturnedVariants: ...


def strategy(
    ids: Sequence[str],
    interface: type[Interface],
    score: int | None = None,
) -> Callable[[StrategyFunc[ConcreteInterface]], "Strategy[ConcreteInterface]"]:
    """
    Registers a strategy

    :param ids: The strategy/delegate IDs to register
    :param interface: Which interface type should be dispatched to this strategy
    :param score: Determines precedence of strategies. For example exception
        strategy scores higher than message strategy, so if both interfaces are
        in the event, only exception will be used for hash
    """

    name = interface.path

    if not ids:
        raise TypeError("no ids given")

    def decorator(f: StrategyFunc[ConcreteInterface]) -> Strategy[ConcreteInterface]:
        rv: Strategy[ConcreteInterface] | None = None

        for id in ids:
            STRATEGIES[id] = rv = Strategy(
                id=id, name=name, interface=interface.path, score=score, func=f
            )

        assert rv is not None
        return rv

    return decorator


class GroupingContext:
    def __init__(self, strategy_config: "StrategyConfiguration"):
        # The initial context is essentially the grouping config options
        self._stack = [strategy_config.initial_context]
        self.config = strategy_config
        self.push()
        self["variant"] = None

    def __setitem__(self, key: str, value: ContextValue) -> None:
        self._stack[-1][key] = value

    def __getitem__(self, key: str) -> ContextValue:
        # Walk down the stack from the top and return the first instance of `key` found
        for d in reversed(self._stack):
            if key in d:
                return d[key]
        raise KeyError(key)

    def __enter__(self) -> "GroupingContext":
        self.push()
        return self

    def __exit__(self, exc_type: type[Exception], exc_value: Exception, tb: Any) -> None:
        self.pop()

    def push(self) -> None:
        self._stack.append({})

    def pop(self) -> None:
        self._stack.pop()

    def get_grouping_components_by_variant(
        self, interface: Interface, *, event: Event, **kwargs: Any
    ) -> ReturnedVariants:
        """Invokes a delegate grouping strategy.  If no such delegate is
        configured a fallback grouping component is returned.
        """
        return self._get_strategy_dict(interface, event=event, **kwargs)

    @overload
    def get_single_grouping_component(
        self, interface: Frame, *, event: Event, **kwargs: Any
    ) -> FrameGroupingComponent: ...

    @overload
    def get_single_grouping_component(
        self, interface: SingleException, *, event: Event, **kwargs: Any
    ) -> ExceptionGroupingComponent: ...

    @overload
    def get_single_grouping_component(
        self, interface: Stacktrace, *, event: Event, **kwargs: Any
    ) -> StacktraceGroupingComponent: ...

    def get_single_grouping_component(
        self, interface: Interface, *, event: Event, **kwargs: Any
    ) -> BaseGroupingComponent:
        """Invokes a delegate grouping strategy.  If no such delegate is
        configured a fallback grouping component is returned.
        """
        rv = self._get_strategy_dict(interface, event=event, **kwargs)

        assert len(rv) == 1
        return rv[self["variant"]]

    def _get_strategy_dict(
        self, interface: Interface, *, event: Event, **kwargs: Any
    ) -> ReturnedVariants:
        path = interface.path
        strategy = self.config.delegates.get(path)
        if strategy is None:
            raise RuntimeError(f"failed to dispatch interface {path} to strategy")

        kwargs["context"] = self
        kwargs["event"] = event
        rv = strategy(interface, **kwargs)
        assert isinstance(rv, dict)

        return rv


def lookup_strategy(strategy_id: str) -> "Strategy[Any]":
    """Looks up a strategy by id."""
    try:
        return STRATEGIES[strategy_id]
    except KeyError:
        raise LookupError("Unknown strategy %r" % strategy_id)


class Strategy(Generic[ConcreteInterface]):
    """Baseclass for all strategies."""

    def __init__(
        self,
        id: str,
        name: str,
        interface: str,
        score: int | None,
        func: StrategyFunc[ConcreteInterface],
    ):
        self.id = id
        self.strategy_class = id.split(":", 1)[0]
        self.name = name
        self.interface_name = interface
        self.score = score
        self.func = func
        self.variant_processor_func: VariantProcessor | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r}>"

    def _invoke(
        self, func: Callable[..., ReturnedVariants], *args: Any, **kwargs: Any
    ) -> ReturnedVariants:
        # We forcefully override strategy here. This lets a strategy
        # function always access its metadata and directly forward it to
        # subcomponents.
        kwargs["strategy"] = self
        return func(*args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> ReturnedVariants:
        return self._invoke(self.func, *args, **kwargs)

    def variant_processor(self, func: VariantProcessor) -> VariantProcessor:
        """Registers a variant reducer function that can be used to postprocess
        all variants created from this strategy.
        """
        self.variant_processor_func = func
        return func

    def get_grouping_component(
        self, event: Event, context: GroupingContext, variant: str | None = None
    ) -> None | BaseGroupingComponent | ReturnedVariants:
        """Given a specific variant this calculates the grouping component."""
        args = []
        iface = event.interfaces.get(self.interface_name)
        if iface is None:
            return None
        args.append(iface)
        with context:
            # If a variant is passed put it into the context
            if variant is not None:
                context["variant"] = variant
            return self(event=event, context=context, *args)

    def get_grouping_components(self, event: Event, context: GroupingContext) -> ReturnedVariants:
        """This returns a dictionary of all components by variant that this
        strategy can produce.
        """

        # strategy can decide on its own which variants to produce and which contribute
        components_by_variant = self.get_grouping_component(event, variant=None, context=context)
        if components_by_variant is None:
            return {}

        assert isinstance(components_by_variant, dict)

        final_components_by_variant = {}
        priority_contributing_variants_by_hash = {}
        non_priority_contributing_variants = []

        for variant_name, component in components_by_variant.items():
            is_priority = variant_name.startswith("!")
            variant_name = variant_name.lstrip("!")

            if component.contributes:
                # Track priority and non-priority contributing hashes separately, so the latter can
                # be deduped against the former
                if is_priority:
                    priority_contributing_variants_by_hash[component.get_hash()] = variant_name
                else:
                    non_priority_contributing_variants.append(variant_name)

            final_components_by_variant[variant_name] = component

        # Mark any non-priority duplicates of priority hashes as non-contributing
        for variant_name in non_priority_contributing_variants:
            component = final_components_by_variant[variant_name]
            hash_value = component.get_hash()
            duplicate_of = priority_contributing_variants_by_hash.get(hash_value)
            if duplicate_of is not None:
                component.update(
                    contributes=False,
                    hint="ignored because hash matches %s variant" % duplicate_of,
                )

        if self.variant_processor_func is not None:
            final_components_by_variant = self._invoke(
                self.variant_processor_func,
                final_components_by_variant,
                event=event,
                context=context,
            )
        return final_components_by_variant


class StrategyConfiguration:
    id: str | None
    base: type["StrategyConfiguration"] | None = None
    config_class = None
    strategies: dict[str, Strategy[Any]] = {}
    delegates: dict[str, Strategy[Any]] = {}
    changelog: str | None = None
    hidden = False
    risk = RISK_LEVEL_LOW
    initial_context: ContextDict = {}
    enhancements_base: str | None = DEFAULT_GROUPING_ENHANCEMENTS_BASE
    fingerprinting_bases: Sequence[str] | None = DEFAULT_GROUPING_FINGERPRINTING_BASES

    def __init__(self, enhancements: str | None = None, **extra: Any):
        if enhancements is None:
            enhancements_instance = Enhancements.from_config_string("")
        else:
            enhancements_instance = Enhancements.loads(enhancements)
        self.enhancements = enhancements_instance

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.id!r}>"

    def iter_strategies(self) -> Iterator[Strategy[Any]]:
        """Iterates over all strategies by highest score to lowest."""
        return iter(sorted(self.strategies.values(), key=lambda x: x.score and -x.score or 0))

    @classmethod
    def as_dict(cls) -> dict[str, Any]:
        return {
            "id": cls.id,
            "base": cls.base.id if cls.base else None,
            "strategies": sorted(cls.strategies),
            "changelog": cls.changelog,
            "delegates": sorted(x.id for x in cls.delegates.values()),
            "hidden": cls.hidden,
            "risk": cls.risk,
            "latest": projectoptions.lookup_well_known_key("sentry:grouping_config").get_default(
                epoch=projectoptions.LATEST_EPOCH
            )
            == cls.id,
        }


def create_strategy_configuration(
    id: str | None,
    strategies: Sequence[str] | None = None,
    delegates: Sequence[str] | None = None,
    changelog: str | None = None,
    hidden: bool = False,
    base: type[StrategyConfiguration] | None = None,
    risk: Risk | None = None,
    initial_context: ContextDict | None = None,
    enhancements_base: str | None = None,
    fingerprinting_bases: Sequence[str] | None = None,
) -> type[StrategyConfiguration]:
    """Declares a new strategy configuration.

    Values can be inherited from a base configuration.  For strategies if there is
    a strategy of the same class it's replaced.  For delegates if there is a
    delegation for the same interface it's replaced.

    It's impossible to remove a strategy of a class when a base is declared (same
    for delegates).
    """

    class NewStrategyConfiguration(StrategyConfiguration):
        pass

    NewStrategyConfiguration.id = id
    NewStrategyConfiguration.base = base
    NewStrategyConfiguration.strategies = dict(base.strategies) if base else {}
    NewStrategyConfiguration.delegates = dict(base.delegates) if base else {}
    NewStrategyConfiguration.initial_context = dict(base.initial_context) if base else {}
    NewStrategyConfiguration.enhancements_base = base.enhancements_base if base else None
    if base and base.fingerprinting_bases is not None:
        NewStrategyConfiguration.fingerprinting_bases = list(base.fingerprinting_bases)
    else:
        NewStrategyConfiguration.fingerprinting_bases = None

    if risk is None:
        risk = RISK_LEVEL_LOW
    NewStrategyConfiguration.risk = risk
    NewStrategyConfiguration.hidden = hidden

    by_class: dict[str, list[str]] = {}
    for strategy in NewStrategyConfiguration.strategies.values():
        by_class.setdefault(strategy.strategy_class, []).append(strategy.id)

    for strategy_id in strategies or {}:
        strategy = lookup_strategy(strategy_id)
        if strategy.score is None:
            raise RuntimeError(f"Unscored strategy {strategy_id} added to {id}")
        for old_id in by_class.get(strategy.strategy_class) or ():
            NewStrategyConfiguration.strategies.pop(old_id, None)
        NewStrategyConfiguration.strategies[strategy_id] = strategy

    new_delegates = set()
    for strategy_id in delegates or ():
        strategy = lookup_strategy(strategy_id)
        if strategy.interface_name in new_delegates:
            raise RuntimeError(
                "duplicate interface match for "
                "delegate %r (conflict on %r)" % (id, strategy.interface_name)
            )
        NewStrategyConfiguration.delegates[strategy.interface_name] = strategy
        new_delegates.add(strategy.interface_name)

    if initial_context:
        NewStrategyConfiguration.initial_context.update(initial_context)

    if enhancements_base:
        NewStrategyConfiguration.enhancements_base = enhancements_base

    if fingerprinting_bases:
        NewStrategyConfiguration.fingerprinting_bases = fingerprinting_bases

    NewStrategyConfiguration.changelog = inspect.cleandoc(changelog or "")
    NewStrategyConfiguration.__name__ = "StrategyConfiguration(%s)" % id
    return NewStrategyConfiguration


def produces_variants(
    variants: Sequence[str],
) -> Callable[[StrategyFunc[ConcreteInterface]], StrategyFunc[ConcreteInterface]]:
    """
    A grouping strategy can either:

    - be told by the caller which variant to generate
    - determine its own variants

    In the latter case, use this decorator to produce variants and eliminate
    duplicate hashes.

    Syntax::

        # call decorated function twice with different variant values
        # (returning a new variant dictionary)
        #
        # Return value is a dictionary of `{"system": ..., "app": ...}`.
        @produces_variants(["system", "app"])

        # discard app variant if system variant produces the same hash, or if
        # the function returned None when invoked with `context['variant'] ==
        # 'system'`. The actual logic for discarding is within
        # `Component.get_grouping_component_variants`, so hashes are compared
        # at the outermost level of the tree.
        #
        # Return value is a dictionary of `{"!system": ..., "app": ...}`,
        # however function is still called with `"system"` as
        # `context["variant"]`.
        @produces_variants(["!system", "app"])
    """

    def decorator(f: StrategyFunc[ConcreteInterface]) -> StrategyFunc[ConcreteInterface]:
        def inner(*args: Any, **kwargs: Any) -> ReturnedVariants:
            return call_with_variants(f, variants, *args, **kwargs)

        return inner

    return decorator


def call_with_variants(
    f: Callable[..., ReturnedVariants],
    variants_to_produce: Sequence[str],
    *args: Any,
    **kwargs: Any,
) -> ReturnedVariants:
    context = kwargs["context"]
    if context["variant"] is not None:
        # For the case where the variant is already determined, we act as a
        # delegate strategy.
        #
        # To ensure the function can deal with the particular value we assert
        # the variant name is one of our own though.
        assert (
            context["variant"] in variants_to_produce
            or "!" + context["variant"] in variants_to_produce
        )
        return f(*args, **kwargs)

    rv = {}

    for variant_name in variants_to_produce:
        with context:
            context["variant"] = variant_name.lstrip("!")
            rv_variants = f(*args, **kwargs)
            assert len(rv_variants) == 1
            component = rv_variants[variant_name.lstrip("!")]

        rv[variant_name] = component

    return rv
