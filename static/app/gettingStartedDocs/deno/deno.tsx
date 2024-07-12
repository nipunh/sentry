import ExternalLink from 'sentry/components/links/externalLink';
import {StepType} from 'sentry/components/onboarding/gettingStartedDoc/step';
import type {
  Docs,
  DocsParams,
  OnboardingConfig,
} from 'sentry/components/onboarding/gettingStartedDoc/types';
import replayOnboardingJsLoader from 'sentry/gettingStartedDocs/javascript/jsLoader/jsLoader';
import {t, tct} from 'sentry/locale';

type Params = DocsParams;

const getInstallConfig = () => [
  {
    code: [
      {
        label: 'Deno registry',
        value: 'deno',
        language: 'javascript',
        code: `import * as Sentry from "https://deno.land/x/sentry/index.mjs";"`,
      },
      {
        label: 'npm registry',
        value: 'npm',
        language: 'javascript',
        code: `import * as Sentry from "npm:@sentry/deno";`,
      },
    ],
  },
];

const getConfigureSnippet = (params: Params) =>
  `
Sentry.init({
  dsn: "${params.dsn}",${
    params.isPerformanceSelected
      ? `
  // enable performance
  tracesSampleRate: 1.0,`
      : ''
  }
});
`;

const getVerifySnippet = () => `;
setTimeout(() => {
  throw new Error();
});
`;

const getMetricsConfigureSnippet = (params: DocsParams) => `;
Sentry.init({
  dsn: '${params.dsn}',
  // Only needed for SDK versions < 8.0.0
  // _experiments: {
  //   metricsAggregator: true,
  // },
});
`;

const getMetricsVerifySnippet = () => `;
// Add 4 to a counter named 'hits'
Sentry.metrics.increment('hits', 4);
`;

const onboarding: OnboardingConfig = {
  install: () => [
    {
      type: StepType.INSTALL,
      description: t(
        "Sentry captures data by using an SDK within your application's runtime."
      ),
      configurations: getInstallConfig(),
    },
  ],
  configure: params => [
    {
      type: StepType.CONFIGURE,
      description: t(
        "Initialize Sentry as early as possible in your application's lifecycle."
      ),
      configurations: [
        {
          language: 'javascript',
          code: getConfigureSnippet(params),
        },
      ],
    },
  ],
  verify: () => [
    {
      type: StepType.VERIFY,
      description: t(
        "This snippet contains an intentional error and can be used as a test to make sure that everything's working as expected."
      ),
      configurations: [
        {
          language: 'javascript',
          code: getVerifySnippet(),
        },
      ],
    },
  ],
  nextSteps: params =>
    params.isPerformanceSelected
      ? []
      : [
          {
            id: 'performance-monitoring',
            name: t('Performance Monitoring'),
            description: t(
              'Track down transactions to connect the dots between 10-second page loads and poor-performing API calls or slow database queries.'
            ),
            link: 'https://docs.sentry.io/platforms/javascript/guides/bun/tracing/',
          },
        ],
};

const customMetricsOnboarding: OnboardingConfig = {
  install: () => [
    {
      type: StepType.INSTALL,
      description: tct(
        'You need a minimum version [codeVersion:7.91.0] of [codePackage:@sentry/deno].',
        {
          codeVersion: <code />,
          codePackage: <code />,
        }
      ),
      configurations: getInstallConfig(),
    },
  ],
  configure: params => [
    {
      type: StepType.CONFIGURE,
      description: t(
        'With the default snippet in place, there is no need for any further configuration.'
      ),
      configurations: [
        {
          code: getMetricsConfigureSnippet(params),
          language: 'javascript',
        },
      ],
    },
  ],
  verify: () => [
    {
      type: StepType.VERIFY,
      description: tct(
        "Then you'll be able to add metrics as [codeCounters:counters], [codeSets:sets], [codeDistribution:distributions], and [codeGauge:gauges]. These are available under the [codeNamespace:Sentry.metrics] namespace. This API is available in both renderer and main processes. Try out this example:",
        {
          codeCounters: <code />,
          codeSets: <code />,
          codeDistribution: <code />,
          codeGauge: <code />,
          codeNamespace: <code />,
        }
      ),
      configurations: [
        {
          code: [
            {
              label: 'JavaScript',
              value: 'javascript',
              language: 'javascript',
              code: getMetricsVerifySnippet(),
            },
          ],
        },
        {
          description: t(
            'It can take up to 3 minutes for the data to appear in the Sentry UI.'
          ),
        },
        {
          description: tct(
            'Learn more about metrics and how to configure them, by reading the [docsLink:docs].',
            {
              docsLink: (
                <ExternalLink href="https://docs.sentry.io/platforms/javascript/guides/deno/metrics/" />
              ),
            }
          ),
        },
      ],
    },
  ],
};

const docs: Docs = {
  onboarding,
  replayOnboardingJsLoader,
  customMetricsOnboarding,
};

export default docs;
