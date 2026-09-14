import type { ReactNode } from "react";

import styles from "./LoadingSkeletons.module.css";

type LoadingRegionProps = {
  label: string;
  children: ReactNode;
  className?: string;
};

function LoadingRegion({ label, children, className = "" }: LoadingRegionProps) {
  return (
    <section
      className={`${styles.loadingRegion} ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span className={styles.srOnly}>{label}</span>
      <div className={styles.skeletonCanvas} aria-hidden="true">
        {children}
      </div>
    </section>
  );
}

function Block({ className = "" }: { className?: string }) {
  return <span className={`${styles.block} ${className}`.trim()} />;
}

export function DocumentLibrarySkeleton() {
  return (
    <LoadingRegion label="Đang tải thư viện quy chế" className={styles.documentLibrary}>
      <header className={styles.introduction}>
        <Block className={styles.pageTitle} />
        <Block className={styles.pageDescription} />
      </header>

      <div className={styles.filterGrid}>
        <div className={styles.searchSkeleton}>
          <Block className={styles.fieldLabel} />
          <Block className={styles.fieldControl} />
        </div>
        {Array.from({ length: 3 }, (_, index) => (
          <div className={styles.filterSkeleton} key={`document-filter-${index}`}>
            <Block className={styles.fieldLabel} />
            <Block className={styles.fieldControl} />
          </div>
        ))}
      </div>

      <div className={styles.resultSummary}>
        <Block className={styles.resultCount} />
      </div>

      <div className={styles.documentRows}>
        {Array.from({ length: 5 }, (_, index) => (
          <div className={styles.documentRow} key={`document-row-${index}`}>
            <Block className={styles.documentIcon} />
            <div className={styles.documentCopy}>
              <Block className={index % 2 === 0 ? styles.longTitle : styles.mediumTitle} />
              <Block className={styles.documentMeta} />
            </div>
            <Block className={styles.statusBadge} />
            <Block className={styles.rowAction} />
          </div>
        ))}
      </div>
    </LoadingRegion>
  );
}

export function AdminTableSkeleton({ variant = "documents" }: { variant?: "documents" | "users" }) {
  const columnClass = variant === "users" ? styles.userColumns : styles.documentColumns;
  const label = variant === "users" ? "Đang tải danh sách người dùng" : "Đang tải danh sách tài liệu";

  return (
    <LoadingRegion label={label} className={styles.adminPage}>
      <header className={styles.adminHeading}>
        <div>
          <Block className={styles.adminTitle} />
          <Block className={styles.adminDescription} />
        </div>
        <Block className={styles.primaryAction} />
      </header>

      <div className={styles.metricGrid}>
        {Array.from({ length: 4 }, (_, index) => (
          <div className={styles.metricCard} key={`admin-metric-${index}`}>
            <Block className={styles.metricIcon} />
            <div>
              <Block className={styles.metricLabel} />
              <Block className={styles.metricValue} />
            </div>
          </div>
        ))}
      </div>

      <div className={styles.tablePanel}>
        <div className={styles.tableToolbar}>
          <Block className={styles.searchControl} />
          <Block className={styles.filterControl} />
        </div>
        <div className={`${styles.tableHeader} ${columnClass}`}>
          {Array.from({ length: variant === "users" ? 6 : 7 }, (_, index) => (
            <Block className={styles.columnLabel} key={`table-heading-${index}`} />
          ))}
        </div>
        <div className={styles.tableRows}>
          {Array.from({ length: 6 }, (_, rowIndex) => (
            <div className={`${styles.tableRow} ${columnClass}`} key={`table-row-${rowIndex}`}>
              {Array.from({ length: variant === "users" ? 6 : 7 }, (_, cellIndex) => (
                <Block
                  className={cellIndex === 0 ? styles.primaryCell : styles.tableCell}
                  key={`table-cell-${rowIndex}-${cellIndex}`}
                />
              ))}
            </div>
          ))}
        </div>
        <div className={styles.tableFooter}>
          <Block className={styles.footerCount} />
          <Block className={styles.footerPagination} />
        </div>
      </div>
    </LoadingRegion>
  );
}

export function AdminDashboardSkeleton() {
  return (
    <LoadingRegion label="Đang tải tổng quan hệ thống" className={styles.dashboardPage}>
      <div className={styles.dashboardHero}>
        <div>
          <Block className={styles.dashboardTitle} />
          <Block className={styles.dashboardDescription} />
          <Block className={styles.dashboardDescriptionShort} />
        </div>
        <Block className={styles.primaryAction} />
      </div>

      <div className={styles.dashboardMetrics}>
        {Array.from({ length: 4 }, (_, index) => (
          <div className={styles.dashboardMetric} key={`dashboard-metric-${index}`}>
            <Block className={styles.dashboardMetricIcon} />
            <div>
              <Block className={styles.metricLabel} />
              <Block className={styles.metricValue} />
              <Block className={styles.metricNote} />
            </div>
          </div>
        ))}
      </div>

      <div className={styles.analyticsGrid}>
        {Array.from({ length: 3 }, (_, index) => (
          <div className={styles.dashboardPanel} key={`analytics-panel-${index}`}>
            <PanelHeadingSkeleton />
            <div className={styles.chartSkeleton}>
              <Block className={index === 0 ? styles.chartCircle : styles.chartLead} />
              <div className={styles.chartLines}>
                <Block />
                <Block />
                <Block />
                <Block />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.dashboardBottomGrid}>
        <div className={styles.dashboardPanel}>
          <PanelHeadingSkeleton />
          <div className={styles.compactRows}>
            {Array.from({ length: 4 }, (_, index) => (
              <div key={`compact-row-${index}`}>
                <Block className={styles.compactIcon} />
                <span>
                  <Block className={styles.compactTitle} />
                  <Block className={styles.compactMeta} />
                </span>
                <Block className={styles.statusBadge} />
              </div>
            ))}
          </div>
        </div>
        <div className={styles.dashboardPanel}>
          <PanelHeadingSkeleton />
          <div className={styles.healthSkeleton}>
            <Block className={styles.healthValue} />
            <Block className={styles.healthLabel} />
            <Block className={styles.healthBar} />
            <Block className={styles.healthNote} />
          </div>
        </div>
      </div>
    </LoadingRegion>
  );
}

function PanelHeadingSkeleton() {
  return (
    <div className={styles.panelHeading}>
      <Block className={styles.panelIcon} />
      <div>
        <Block className={styles.panelTitle} />
        <Block className={styles.panelDescription} />
      </div>
    </div>
  );
}

export function AskPageSkeleton() {
  return (
    <LoadingRegion label="Đang chuẩn bị trang hỏi PolicyMate AI" className={styles.askPage}>
      <header className={styles.introduction}>
        <Block className={styles.askTitle} />
        <Block className={styles.askDescription} />
      </header>
      <div className={styles.composerSkeleton}>
        <Block className={styles.composerLine} />
        <div>
          <Block className={styles.composerHint} />
          <Block className={styles.composerButton} />
        </div>
      </div>
      <div className={styles.askGrid}>
        <AnswerResultSkeleton decorative />
        <SourceListSkeleton decorative />
      </div>
    </LoadingRegion>
  );
}

export function AnswerResultSkeleton({ decorative = false }: { decorative?: boolean }) {
  const content = (
    <div className={styles.answerCard}>
      <div className={styles.answerHeading}>
        <Block className={styles.answerIcon} />
        <span>
          <Block className={styles.answerTitle} />
          <Block className={styles.answerMeta} />
        </span>
      </div>
      <div className={styles.answerLines}>
        <Block />
        <Block />
        <Block className={styles.answerLineShort} />
        <Block />
        <Block className={styles.answerLineMedium} />
      </div>
    </div>
  );

  if (decorative) return content;
  return <LoadingRegion label="PolicyMate đang tổng hợp câu trả lời">{content}</LoadingRegion>;
}

export function SourceListSkeleton({ decorative = false }: { decorative?: boolean }) {
  const content = (
    <aside className={styles.sourcePanel} aria-hidden={decorative || undefined}>
      <div className={styles.sourceHeading}>
        <Block className={styles.sourceHeadingIcon} />
        <Block className={styles.sourceHeadingTitle} />
      </div>
      {Array.from({ length: 2 }, (_, index) => (
        <div className={styles.sourceCard} key={`source-skeleton-${index}`}>
          <Block className={styles.sourceType} />
          <Block className={styles.sourceTitle} />
          <Block className={styles.sourceTitleShort} />
          <div className={styles.sourceMetadata}>
            <Block />
            <Block />
          </div>
        </div>
      ))}
    </aside>
  );

  if (decorative) return content;
  return <LoadingRegion label="Đang xác minh nguồn đối chiếu">{content}</LoadingRegion>;
}

export function DocumentDetailSkeleton() {
  return (
    <LoadingRegion label="Đang tải chi tiết văn bản" className={styles.detailPage}>
      <div className={styles.detailHeader}>
        <div>
          <Block className={styles.detailTitle} />
          <Block className={styles.detailSubtitle} />
        </div>
        <Block className={styles.statusBadge} />
      </div>
      <div className={styles.detailGrid}>
        <aside className={styles.detailInfo}>
          <Block className={styles.detailSectionTitle} />
          {Array.from({ length: 5 }, (_, index) => (
            <div className={styles.detailField} key={`detail-field-${index}`}>
              <Block className={styles.detailLabel} />
              <Block className={index % 2 === 0 ? styles.detailValue : styles.detailValueShort} />
            </div>
          ))}
        </aside>
        <div className={styles.documentViewer}>
          <div className={styles.viewerHeader}>
            <div>
              <Block className={styles.detailSectionTitle} />
              <Block className={styles.viewerDescription} />
            </div>
            <Block className={styles.viewerAction} />
          </div>
          <div className={styles.viewerBody}>
            <Block className={styles.documentSheet} />
          </div>
        </div>
      </div>
    </LoadingRegion>
  );
}
