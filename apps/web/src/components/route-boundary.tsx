import { Component, Suspense, type ReactNode } from 'react';
import { useI18n } from '../lib/i18n';

class RouteErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function RouteBoundary({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  return <RouteErrorBoundary fallback={
    <section className="panel">
      <p role="alert">{t('Không tải được trang. Tải lại để thử lại.', 'Could not load this page. Reload to try again.')}</p>
      <button onClick={() => window.location.reload()}>{t('Tải lại trang', 'Reload page')}</button>
    </section>
  }>
    <Suspense fallback={<section className="panel" role="status">{t('Đang tải trang…', 'Loading page…')}</section>}>
      {children}
    </Suspense>
  </RouteErrorBoundary>;
}
