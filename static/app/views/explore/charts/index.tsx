import {Fragment, useCallback, useMemo} from 'react';
import styled from '@emotion/styled';

import {getInterval} from 'sentry/components/charts/utils';
import {CompactSelect} from 'sentry/components/compactSelect';
import {CHART_PALETTE} from 'sentry/constants/chartPalette';
import {IconClock, IconGraph} from 'sentry/icons';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import {dedupeArray} from 'sentry/utils/dedupeArray';
import {
  aggregateOutputType,
  formatParsedFunction,
  parseFunction,
} from 'sentry/utils/discover/fields';
import {MutableSearch} from 'sentry/utils/tokenizeSearch';
import usePageFilters from 'sentry/utils/usePageFilters';
import {formatVersion} from 'sentry/utils/versions/formatVersion';
import {useChartInterval} from 'sentry/views/explore/hooks/useChartInterval';
import {useDataset} from 'sentry/views/explore/hooks/useDataset';
import {useVisualizes} from 'sentry/views/explore/hooks/useVisualizes';
import Chart, {
  ChartType,
  useSynchronizeCharts,
} from 'sentry/views/insights/common/components/chart';
import ChartPanel from 'sentry/views/insights/common/components/chartPanel';
import {useSortedTimeSeries} from 'sentry/views/insights/common/queries/useSortedTimeSeries';
import {CHART_HEIGHT} from 'sentry/views/insights/database/settings';

import {useGroupBys} from '../hooks/useGroupBys';
import {useResultMode} from '../hooks/useResultsMode';
import {useSorts} from '../hooks/useSorts';
import {TOP_EVENTS_LIMIT, useTopEvents} from '../hooks/useTopEvents';
import {formatSort} from '../tables/aggregatesTable';

interface ExploreChartsProps {
  query: string;
}

const exploreChartTypeOptions = [
  {
    value: ChartType.LINE,
    label: t('Line'),
  },
  {
    value: ChartType.AREA,
    label: t('Area'),
  },
  {
    value: ChartType.BAR,
    label: t('Bar'),
  },
];

export const EXPLORE_CHART_GROUP = 'explore-charts_group';

// TODO: Update to support aggregate mode and multiple queries / visualizations
export function ExploreCharts({query}: ExploreChartsProps) {
  const pageFilters = usePageFilters();

  const [dataset] = useDataset();
  const [visualizes, setVisualizes] = useVisualizes();
  const [interval, setInterval, intervalOptions] = useChartInterval();
  const {groupBys} = useGroupBys();
  const [resultMode] = useResultMode();
  const topEvents = useTopEvents();

  const fields: string[] = useMemo(() => {
    if (resultMode === 'samples') {
      return [];
    }

    return [...groupBys, ...visualizes.flatMap(visualize => visualize.yAxes)].filter(
      Boolean
    );
  }, [resultMode, groupBys, visualizes]);
  const [sorts] = useSorts({fields});

  const orderby: string | string[] | undefined = useMemo(() => {
    if (!sorts.length) {
      return undefined;
    }

    return sorts.map(formatSort);
  }, [sorts]);

  const yAxes = useMemo(() => {
    const deduped = dedupeArray(visualizes.flatMap(visualize => visualize.yAxes));
    deduped.sort();
    return deduped;
  }, [visualizes]);

  const timeSeriesResult = useSortedTimeSeries(
    {
      search: new MutableSearch(query ?? ''),
      yAxis: yAxes,
      interval: interval ?? getInterval(pageFilters.selection.datetime, 'metrics'),
      fields,
      orderby,
      topEvents,
    },
    'api.explorer.stats',
    dataset
  );

  const getSeries = useCallback(
    (dedupedYAxes: string[]) => {
      return dedupedYAxes.flatMap(yAxis => {
        const series = timeSeriesResult.data[yAxis];
        return series !== undefined ? series : [];
      });
    },
    [timeSeriesResult]
  );

  const handleChartTypeChange = useCallback(
    (chartType: ChartType, index: number) => {
      const newVisualizes = visualizes.slice();
      newVisualizes[index] = {...newVisualizes[index], chartType};
      setVisualizes(newVisualizes);
    },
    [visualizes, setVisualizes]
  );

  useSynchronizeCharts(
    visualizes.length,
    !timeSeriesResult.isPending,
    EXPLORE_CHART_GROUP
  );

  return (
    <Fragment>
      {visualizes.map((visualize, index) => {
        const dedupedYAxes = dedupeArray(visualize.yAxes);

        const formattedYAxes = dedupedYAxes
          .map(yaxis => {
            const func = parseFunction(yaxis);
            return func ? formatParsedFunction(func) : undefined;
          })
          .filter(Boolean);

        const {chartType} = visualize;
        const chartIcon =
          chartType === ChartType.LINE
            ? 'line'
            : chartType === ChartType.AREA
              ? 'area'
              : 'bar';

        return (
          <ChartContainer key={index}>
            <ChartPanel>
              <ChartHeader>
                <ChartTitle>{formattedYAxes.join(',')}</ChartTitle>
                <ChartSettingsContainer>
                  <CompactSelect
                    triggerLabel=""
                    triggerProps={{
                      icon: <IconGraph type={chartIcon} />,
                      borderless: true,
                      showChevron: false,
                      size: 'sm',
                    }}
                    value={chartType}
                    menuTitle="Type"
                    options={exploreChartTypeOptions}
                    onChange={option => handleChartTypeChange(option.value, index)}
                  />
                  <CompactSelect
                    triggerLabel=""
                    value={interval}
                    onChange={({value}) => setInterval(value)}
                    triggerProps={{
                      icon: <IconClock />,
                      borderless: true,
                      showChevron: false,
                      size: 'sm',
                    }}
                    menuTitle="Interval"
                    options={intervalOptions}
                  />
                </ChartSettingsContainer>
              </ChartHeader>
              <Chart
                height={CHART_HEIGHT}
                grid={{
                  left: '0',
                  right: '0',
                  top: '8px',
                  bottom: '0',
                }}
                legendFormatter={value => formatVersion(value)}
                data={getSeries(dedupedYAxes)}
                error={timeSeriesResult.error}
                loading={timeSeriesResult.isPending}
                chartGroup={EXPLORE_CHART_GROUP}
                // TODO Abdullah: Make chart colors dynamic, with changing topN events count and overlay count.
                chartColors={CHART_PALETTE[TOP_EVENTS_LIMIT - 1]}
                type={chartType}
                // for now, use the first y axis unit
                aggregateOutputFormat={aggregateOutputType(dedupedYAxes[0])}
              />
            </ChartPanel>
          </ChartContainer>
        );
      })}
    </Fragment>
  );
}

const ChartContainer = styled('div')`
  display: grid;
  gap: 0;
  grid-template-columns: 1fr;
  margin-bottom: ${space(2)};
`;

const ChartHeader = styled('div')`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
`;

const ChartTitle = styled('div')`
  ${p => p.theme.text.cardTitle}
`;

const ChartSettingsContainer = styled('div')`
  display: flex;
`;
