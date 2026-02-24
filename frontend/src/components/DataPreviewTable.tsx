import type { DatasetInfo } from "../types";

interface DataPreviewTableProps {
  datasetInfo: DatasetInfo;
  highlightedColumns?: Set<string>;
}

export function DataPreviewTable({ datasetInfo, highlightedColumns }: DataPreviewTableProps) {
  const columns = datasetInfo.columns;
  const rows = datasetInfo.sample_rows;

  return (
    <div className="data-preview-table">
      <div className="data-preview-table__header">
        <span className="data-preview-table__filename">{datasetInfo.filename}</span>
        <span className="data-preview-table__shape">
          {datasetInfo.shape[0]} rows &times; {datasetInfo.shape[1]} cols
        </span>
      </div>
      <div className="data-preview-table__scroll">
        <table className="data-preview-table__table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.name}
                  className={
                    highlightedColumns?.has(col.name)
                      ? "data-preview-table__th data-preview-table__th--highlighted"
                      : "data-preview-table__th"
                  }
                >
                  <div className="data-preview-table__col-name">{col.name}</div>
                  <div className="data-preview-table__col-dtype">{col.dtype}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                {columns.map((col) => (
                  <td
                    key={col.name}
                    className={
                      highlightedColumns?.has(col.name)
                        ? "data-preview-table__td data-preview-table__td--highlighted"
                        : "data-preview-table__td"
                    }
                  >
                    {String(row[col.name] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
