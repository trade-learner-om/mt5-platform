import SwiftUI

struct BacktestResultsPaginationView: View {
    let page: Int
    let pageSize: Int
    let totalCount: Int
    let totalPages: Int
    let disabled: Bool
    let onPageChange: (Int) -> Void
    let onPageSizeChange: (Int) -> Void

    @State private var pageSizeText: String

    init(
        page: Int,
        pageSize: Int,
        totalCount: Int,
        totalPages: Int,
        disabled: Bool,
        onPageChange: @escaping (Int) -> Void,
        onPageSizeChange: @escaping (Int) -> Void
    ) {
        self.page = page
        self.pageSize = pageSize
        self.totalCount = totalCount
        self.totalPages = totalPages
        self.disabled = disabled
        self.onPageChange = onPageChange
        self.onPageSizeChange = onPageSizeChange
        _pageSizeText = State(initialValue: String(pageSize))
    }

    private var rangeStart: Int {
        totalCount == 0 ? 0 : ((page - 1) * pageSize) + 1
    }

    private var rangeEnd: Int {
        totalCount == 0 ? 0 : min(page * pageSize, totalCount)
    }

    private var pageItems: [PageItem] {
        buildPageItems(currentPage: page, totalPages: totalPages)
    }

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Text(totalCount == 0 ? "No results" : "Showing \(rangeStart)–\(rangeEnd) of \(totalCount)")
                    .font(.caption)
                    .foregroundStyle(AppColors.textSecondary)
                Spacer()
                HStack(spacing: 6) {
                    Text("Per page")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppColors.textMuted)
                    TextField("10", text: $pageSizeText)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .frame(width: 52)
                        .padding(.vertical, 6)
                        .padding(.horizontal, 8)
                        .background(AppColors.surfaceMuted)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppColors.border))
                        .disabled(disabled)
                        .onChange(of: pageSizeText) { _, newValue in
                            let clamped = clampPageSize(newValue)
                            if clamped != pageSize {
                                onPageSizeChange(clamped)
                            }
                        }
                }
            }

            if totalPages > 1 {
                HStack(spacing: 6) {
                    paginationButton(title: "Prev", enabled: !disabled && page > 1) {
                        onPageChange(page - 1)
                    }
                    ForEach(pageItems) { item in
                        switch item {
                        case .ellipsis:
                            Text("…")
                                .font(.caption)
                                .foregroundStyle(AppColors.textMuted)
                                .padding(.horizontal, 4)
                        case .page(let value):
                            paginationButton(
                                title: "\(value)",
                                enabled: !disabled,
                                selected: value == page
                            ) {
                                onPageChange(value)
                            }
                        }
                    }
                    paginationButton(title: "Next", enabled: !disabled && page < totalPages) {
                        onPageChange(page + 1)
                    }
                }
            }
        }
        .padding(.top, 8)
        .onChange(of: pageSize) { _, newValue in
            pageSizeText = String(newValue)
        }
    }

    @ViewBuilder
    private func paginationButton(title: String, enabled: Bool, selected: Bool = false, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .font(.caption.weight(.semibold))
            .foregroundStyle(selected ? AppColors.accent : AppColors.textPrimary)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(selected ? AppColors.accentSoft : AppColors.surfaceMuted)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(selected ? AppColors.accent.opacity(0.35) : AppColors.border))
            .disabled(!enabled)
            .opacity(enabled ? 1 : 0.45)
    }
}

private enum PageItem: Identifiable {
    case page(Int)
    case ellipsis

    var id: String {
        switch self {
        case .page(let value): return "page-\(value)"
        case .ellipsis: return "ellipsis"
        }
    }
}

private func clampPageSize(_ value: String) -> Int {
    let parsed = Int(value.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 10
    return min(50, max(1, parsed))
}

private func buildPageItems(currentPage: Int, totalPages: Int) -> [PageItem] {
    if totalPages <= 1 { return [.page(1)] }
    if totalPages <= 7 {
        return (1...totalPages).map { .page($0) }
    }
    var pages = Set([1, totalPages, currentPage, currentPage - 1, currentPage + 1])
    let sorted = pages.filter { $0 >= 1 && $0 <= totalPages }.sorted()
    var items: [PageItem] = []
    for (index, value) in sorted.enumerated() {
        if index > 0, value - sorted[index - 1] > 1 {
            items.append(.ellipsis)
        }
        items.append(.page(value))
    }
    return items
}
