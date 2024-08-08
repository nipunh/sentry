import styled from '@emotion/styled';

import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';

type Props = {
  culture?: string;
  filePath?: string | null;
  name?: string;
  publicKeyToken?: string;
  version?: string;
};

function Assembly({name, version, culture, publicKeyToken}: Props) {
  return (
    <AssemblyWrapper>
      <AssemblyInfo>
        <Caption>Assembly:</Caption>
        {name || '-'}
      </AssemblyInfo>
      <AssemblyInfo>
        <Caption>{t('Version')}:</Caption>
        {version || '-'}
      </AssemblyInfo>

      {culture && (
        <AssemblyInfo>
          <Caption>{t('Culture')}:</Caption>
          {culture}
        </AssemblyInfo>
      )}

      {publicKeyToken && (
        <AssemblyInfo>
          <Caption>PublicKeyToken:</Caption>
          {publicKeyToken}
        </AssemblyInfo>
      )}
    </AssemblyWrapper>
  );
}

const AssemblyWrapper = styled('div')`
  font-size: 80%;
  display: flex;
  flex-wrap: wrap;
  color: ${p => p.theme.textColor};
  text-align: center;
  position: relative;
  padding: ${p => p.theme.space(0.25)} ${space(3)};
`;

const AssemblyInfo = styled('div')`
  display: flex;
  align-items: center;
  margin-right: ${p => p.theme.space(2)};
`;

const Caption = styled('span')`
  margin-right: 5px;
  font-weight: ${p => p.theme.fontWeightBold};
`;

export {Assembly};
