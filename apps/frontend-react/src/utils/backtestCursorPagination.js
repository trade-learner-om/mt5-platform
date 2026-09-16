export async function fetchBacktestCursorPage(api, token, { targetPage, pageSize, cursors, endpoint }) {
  if (!endpoint) {
    throw new Error("fetchBacktestCursorPage requires an endpoint");
  }
  const request = (cursor) => {
    const params = new URLSearchParams({ limit: String(pageSize) });
    if (cursor) {
      params.set("cursor", cursor);
    }
    return api(`${endpoint}?${params.toString()}`, "GET", undefined, token);
  };

  const nextCursors = { ...cursors };
  const safePage = Math.max(1, Number(targetPage) || 1);

  if (safePage === 1) {
    const data = await request(null);
    if (data?.page_info?.end_cursor) {
      nextCursors[2] = data.page_info.end_cursor;
    }
    return { data, cursors: nextCursors };
  }

  if (Object.prototype.hasOwnProperty.call(nextCursors, safePage)) {
    const data = await request(nextCursors[safePage]);
    if (data?.page_info?.end_cursor) {
      nextCursors[safePage + 1] = data.page_info.end_cursor;
    }
    return { data, cursors: nextCursors };
  }

  let walkPage = 1;
  for (let page = safePage; page >= 1; page -= 1) {
    if (Object.prototype.hasOwnProperty.call(nextCursors, page)) {
      walkPage = page;
      break;
    }
  }

  let cursor = walkPage === 1 ? null : nextCursors[walkPage];
  let data = null;
  for (let page = walkPage; page <= safePage; page += 1) {
    data = await request(page === 1 ? null : cursor);
    if (data?.page_info?.end_cursor) {
      nextCursors[page + 1] = data.page_info.end_cursor;
    }
    cursor = data?.page_info?.end_cursor ?? null;
    if (!data?.page_info?.has_next_page && page < safePage) {
      break;
    }
  }

  return { data, cursors: nextCursors };
}
