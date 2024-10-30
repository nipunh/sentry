import {useState} from 'react';
import {css} from '@emotion/react';
import styled from '@emotion/styled';

import {addErrorMessage, addSuccessMessage} from 'sentry/actionCreators/indicator';
import {Button} from 'sentry/components/button';
import FieldGroup from 'sentry/components/forms/fieldGroup';
import ExternalLink from 'sentry/components/links/externalLink';
import Panel from 'sentry/components/panels/panel';
import PanelBody from 'sentry/components/panels/panelBody';
import PanelHeader from 'sentry/components/panels/panelHeader';
import QuestionTooltip from 'sentry/components/questionTooltip';
import {SegmentedControl} from 'sentry/components/segmentedControl';
import {Tooltip} from 'sentry/components/tooltip';
import {t, tct} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import useOrganization from 'sentry/utils/useOrganization';
import {OrganizationSampleRateField} from 'sentry/views/settings/dynamicSampling/organizationSampleRateField';
import {ProjectsPreviewTable} from 'sentry/views/settings/dynamicSampling/projectsPreviewTable';
import {SamplingModeField} from 'sentry/views/settings/dynamicSampling/samplingModeField';
import {organizationSamplingForm} from 'sentry/views/settings/dynamicSampling/utils/organizationSamplingForm';
import {useUpdateOrganization} from 'sentry/views/settings/dynamicSampling/utils/useUpdateOrganization';
import {useAccess} from 'sentry/views/settings/projectMetrics/access';

const {useFormState, FormProvider} = organizationSamplingForm;

export function OrganizationSampling() {
  const organization = useOrganization();
  const {hasAccess} = useAccess({access: ['org:write']});

  const [period, setPeriod] = useState<'24h' | '30d'>('24h');

  const formState = useFormState({
    targetSampleRate: ((organization.targetSampleRate ?? 1) * 100)?.toLocaleString(),
  });

  const {mutate: updateOrganization, isPending} = useUpdateOrganization();

  const handleSubmit = () => {
    updateOrganization(
      {
        targetSampleRate: Number(formState.fields.targetSampleRate.value) / 100,
      },
      {
        onSuccess: () => {
          addSuccessMessage(t('Changes applied.'));
          formState.save();
        },
        onError: () => {
          addErrorMessage(t('Unable to save changes. Please try again.'));
        },
      }
    );
  };

  const handleReset = () => {
    formState.reset();
  };

  return (
    <FormProvider formState={formState}>
      <form onSubmit={event => event.preventDefault()}>
        <Panel>
          <PanelHeader>{t('Automatic Sampling')}</PanelHeader>
          <PanelBody>
            <FieldGroup
              label={t('Sampling Mode')}
              help={t('Changes the level of detail and configuring sample rates.')}
            >
              <div
                css={css`
                  display: flex;
                  align-items: center;
                  gap: ${space(1)};
                `}
              >
                {t('Automatic Balancing')}{' '}
                <QuestionTooltip
                  size="sm"
                  isHoverable
                  title={tct(
                    'Automatic balancing optimizes the sample rates of your projects based on an overall target for your organization. [link:Learn more]',
                    {
                      // TODO(aknaus): Add link to documentation
                      link: <ExternalLink href="https://docs.sentry.io/" />,
                    }
                  )}
                />
              </div>
            </FieldGroup>
            <SamplingModeField />
            <OrganizationSampleRateField />
          </PanelBody>
        </Panel>
        <FormActions>
          <Button disabled={!formState.hasChanged || isPending} onClick={handleReset}>
            {t('Reset')}
          </Button>
          <Tooltip
            disabled={hasAccess}
            title={t('You do not have permission to update these settings.')}
          >
            <Button
              priority="primary"
              disabled={
                !hasAccess || !formState.isValid || !formState.hasChanged || isPending
              }
              onClick={handleSubmit}
            >
              {t('Save changes')}
            </Button>
          </Tooltip>
        </FormActions>

        <HeadingRow>
          <h4>{t('Project Preview')}</h4>
          <Tooltip
            title={t(
              'The time period for which the projected sample rates are calculated.'
            )}
          >
            <SegmentedControl value={period} onChange={setPeriod} size="xs">
              <SegmentedControl.Item key="24h">{t('24h')}</SegmentedControl.Item>
              <SegmentedControl.Item key="30d">{t('30d')}</SegmentedControl.Item>
            </SegmentedControl>
          </Tooltip>
        </HeadingRow>
        <p>
          {t(
            'The following table gives you a preview of how your projects will be affected by the global sample rate. Depeding on the amount of spans they generate their sample rate will be adjusted. Inactive projects (not listed) will always be sampled at 100% until they generate spans.'
          )}
        </p>
        <ProjectsPreviewTable period={period} />
      </form>
    </FormProvider>
  );
}

const FormActions = styled('div')`
  display: grid;
  grid-template-columns: repeat(2, max-content);
  gap: ${space(1)};
  justify-content: flex-end;
  padding-bottom: ${space(4)};
`;

const HeadingRow = styled('div')`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: ${space(1.5)};

  & > h4 {
    margin: 0;
  }
`;
