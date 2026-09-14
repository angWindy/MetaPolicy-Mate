import type { ReactNode } from "react";
import styles from "./DataTable.module.css";

export type DataTableColumn<Row> = { key: string; header: ReactNode; cell: (row: Row) => ReactNode; align?: "left" | "center" | "right"; width?: string };
export type DataTableProps<Row> = { columns: DataTableColumn<Row>[]; rows: Row[]; getRowKey: (row: Row, index: number) => string | number; caption?: string; emptyMessage?: string; className?: string };
function alignClass(align: DataTableColumn<unknown>["align"]) { return align === "center" ? styles.alignCenter : align === "right" ? styles.alignRight : ""; }
export function DataTable<Row>({ columns, rows, getRowKey, caption, emptyMessage = "Không có dữ liệu", className = "" }: DataTableProps<Row>) {
  return <div className={`${styles.container} ${className}`.trim()}><div className={styles.scroll}><table className={styles.table}>{caption && <caption className={styles.caption}>{caption}</caption>}<thead className={styles.head}><tr>{columns.map((column) => <th key={column.key} className={`${styles.headerCell} ${alignClass(column.align)}`.trim()} scope="col" style={{ width: column.width }}>{column.header}</th>)}</tr></thead><tbody>{rows.length > 0 ? rows.map((row, index) => <tr className={styles.row} key={getRowKey(row, index)}>{columns.map((column) => <td key={column.key} className={`${styles.cell} ${alignClass(column.align)}`.trim()}>{column.cell(row)}</td>)}</tr>) : <tr><td className={styles.empty} colSpan={columns.length}>{emptyMessage}</td></tr>}</tbody></table></div></div>;
}
