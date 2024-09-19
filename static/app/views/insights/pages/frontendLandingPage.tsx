import {Fragment} from 'react';

import {Breadcrumbs, type Crumb} from 'sentry/components/breadcrumbs';
import ButtonBar from 'sentry/components/buttonBar';
import FeedbackWidgetButton from 'sentry/components/feedback/widget/feedbackWidgetButton';
import * as Layout from 'sentry/components/layouts/thirds';
import {TabList, Tabs} from 'sentry/components/tabs';
import {t} from 'sentry/locale';
import {PageAlert} from 'sentry/utils/performance/contexts/pageAlert';
import {ModuleRenderer} from 'sentry/views/insights/pages/moduleRenderer';
import {OVERVIEW_PAGE_TITLE} from 'sentry/views/insights/pages/settings';
import {
  type Filters,
  useFilters,
  useUpdateFilters,
} from 'sentry/views/insights/pages/useFilters';
import {MODULE_TITLES} from 'sentry/views/insights/settings';
import {ModuleName} from 'sentry/views/insights/types';

function FrontendLandingPage() {
  const filters = useFilters();
  const updateFilters = useUpdateFilters();

  const crumbs: Crumb[] = [
    {
      label: t('Performance'),
      to: '/performance', // There is no page at `/insights/` so there is nothing to link to
      preservePageFilters: true,
    },
    {
      label: FRONTEND_LANDING_TITLE,
      to: undefined,
      preservePageFilters: true,
    },
    {
      label: filters.module ? MODULE_TITLES[filters.module] : OVERVIEW_PAGE_TITLE,
      to: undefined,
      preservePageFilters: true,
    },
  ];

  const handleTabChange: (key: Filters['module']) => void = key => {
    if (key === filters.module || (key === OVERVIEW_PAGE_TITLE && !filters.module)) {
      return;
    }
    if (!key) {
      return;
    }
    if (key === OVERVIEW_PAGE_TITLE) {
      updateFilters({module: undefined});
      return;
    }
    updateFilters({module: key});
  };

  return (
    <Fragment>
      <Tabs value={filters.module || OVERVIEW_PAGE_TITLE} onChange={handleTabChange}>
        <Layout.Header>
          <Layout.HeaderContent>
            <Breadcrumbs crumbs={crumbs} />

            <Layout.Title>{FRONTEND_LANDING_TITLE}</Layout.Title>
          </Layout.HeaderContent>
          <Layout.HeaderActions>
            <ButtonBar gap={1}>
              <FeedbackWidgetButton />
            </ButtonBar>
          </Layout.HeaderActions>
          <TabList>
            <TabList.Item key={OVERVIEW_PAGE_TITLE}>{OVERVIEW_PAGE_TITLE}</TabList.Item>
            <TabList.Item key={ModuleName.VITAL}>
              {MODULE_TITLES[ModuleName.VITAL]}
            </TabList.Item>
            <TabList.Item key={ModuleName.HTTP}>
              {MODULE_TITLES[ModuleName.HTTP]}
            </TabList.Item>
            <TabList.Item key={ModuleName.RESOURCE}>
              {MODULE_TITLES[ModuleName.RESOURCE]}
            </TabList.Item>
          </TabList>
        </Layout.Header>
        <Layout.Main fullWidth>
          <PageAlert />
          {!filters.module && 'overview page'}
          {filters.module && <ModuleRenderer />}
        </Layout.Main>
      </Tabs>
    </Fragment>
  );
}

export default FrontendLandingPage;

export const FRONTEND_LANDING_SUB_PATH = 'frontend';
export const FRONTEND_LANDING_TITLE = t('Frontend');
