import Access from 'sentry/components/acl/access';
import type {ButtonProps} from 'sentry/components/button';
import {Button} from 'sentry/components/button';
import Confirm from 'sentry/components/confirm';
import {Tooltip} from 'sentry/components/tooltip';
import {IconDelete} from 'sentry/icons';
import {t} from 'sentry/locale';

interface DebugIdBundleDeleteButtonProps {
  onDelete: () => void;
  size?: ButtonProps['size'];
}

export function DebugIdBundleDeleteButton({
  onDelete,
  size = 'xs',
}: DebugIdBundleDeleteButtonProps) {
  return (
    <Access access={['project:releases']}>
      {({hasAccess}) => (
        <Tooltip
          disabled={hasAccess}
          title={t('You do not have permission to delete source maps.')}
        >
          <Confirm
            onConfirm={onDelete}
            message={t('Are you sure you want to delete these source maps?')}
            disabled={!hasAccess}
          >
            <Button icon={<IconDelete size="xs" />} size={size} disabled={!hasAccess}>
              {t('Delete Source Maps')}
            </Button>
          </Confirm>
        </Tooltip>
      )}
    </Access>
  );
}
