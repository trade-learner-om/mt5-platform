import SwiftUI

struct RootView: View {
    @EnvironmentObject private var vm: AppViewModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var appearanceNow = Date()

    var body: some View {
        ZStack {
            AppColors.background.ignoresSafeArea()
            if vm.state.bootLoading || vm.state.bootStatus == .checkingHost {
                SessionLoaderView(
                    message: vm.state.message,
                    error: vm.state.error,
                    showRetry: !vm.state.bootLoading && !vm.state.error.isEmpty,
                    onRetry: vm.retryPlatformConnection
                )
            } else {
                switch vm.state.bootStatus {
                case .hostRequired:
                    DirectBackendRetryView()
                case .biometricRequired:
                    BiometricGateView()
                case .authRequired:
                    AuthView()
                case .ready:
                    DashboardView()
                case .checkingHost:
                    SessionLoaderView(message: vm.state.message)
                }
            }
        }
        .onAppear { NotificationManager.shared.requestAuthorization() }
        .onChange(of: scenePhase) { phase in
            if phase == .active { vm.onAppForegrounded() }
            appearanceNow = Date()
        }
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { now in
            appearanceNow = now
        }
        .preferredColorScheme(vm.state.appearance.preferredColorScheme(now: appearanceNow))
    }
}

struct SessionLoaderView: View {
    let message: String
    var error: String = ""
    var showRetry = false
    var onRetry: (() -> Void)?

    @State private var pulse = false

    var body: some View {
        ZStack {
            LinearGradient(colors: [LoaderColors.background, LoaderColors.surface, Color(hex: 0x1E1B4B)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()
            VStack(spacing: 18) {
                ZStack {
                    Circle().fill(LoaderColors.accent.opacity(0.12)).frame(width: pulse ? 100 : 88, height: pulse ? 100 : 88)
                    Circle().fill(LoaderColors.accent.opacity(0.22)).frame(width: pulse ? 70 : 60, height: pulse ? 70 : 60)
                    AppBrandIcon(size: 44)
                }
                .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: pulse)
                Text("SignalBridge").font(.title2.weight(.semibold)).foregroundStyle(LoaderColors.text)
                Text(message).font(.subheadline).foregroundStyle(LoaderColors.muted).multilineTextAlignment(.center).padding(.horizontal, 32)
                if !error.isEmpty {
                    Text(error).font(.footnote.weight(.semibold)).foregroundStyle(AppColors.danger).multilineTextAlignment(.center).padding(.horizontal, 24)
                }
                if showRetry, let onRetry {
                    PrimaryButton(title: "Retry connection", action: onRetry)
                        .padding(.horizontal, 32)
                }
            }
        }
        .onAppear { pulse = true }
    }
}

struct DirectBackendRetryView: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        ScrollView {
            SignalCard {
                VStack(alignment: .center, spacing: 14) {
                    ZStack {
                        Circle()
                            .fill(LinearGradient(colors: [AppColors.accent.opacity(0.26), AppColors.sky.opacity(0.18)], startPoint: .topLeading, endPoint: .bottomTrailing))
                            .frame(width: 104, height: 104)
                            .blur(radius: 8)
                        AppBrandIcon(size: 64)
                    }
                    Text("Maintenance mode")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(AppColors.accent)
                        .tracking(1.4)
                    Text("SignalBridge Cloud is temporarily unavailable")
                        .font(.title3.weight(.black))
                        .foregroundStyle(AppColors.textPrimary)
                        .multilineTextAlignment(.center)
                    Text("The backend is currently offline for maintenance or recovery. Retry when service is available again.")
                        .font(.footnote)
                        .foregroundStyle(AppColors.textSecondary)
                        .multilineTextAlignment(.center)
                    ErrorText(text: vm.state.error)
                    PrimaryButton(title: "Retry connection") { vm.saveHostAndConnect() }
                }
            }
            .padding(16)
        }
    }
}

struct BiometricGateView: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var prompted = false

    var body: some View {
        ScrollView {
            SignalCard {
                VStack(spacing: 14) {
                    BrandHeader(subtitle: "Unlock to continue.")
                    Text("Unlock saved login")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(AppColors.textPrimary)
                    Text("Use Face ID or device passcode to open the MT5 platform app.")
                        .font(.footnote).foregroundStyle(AppColors.textSecondary).multilineTextAlignment(.center)
                    ErrorText(text: vm.state.error)
                    PrimaryButton(title: "Unlock") { requestBiometric() }
                    Button("Use password instead") { vm.usePasswordLogin(message: "Please login with your password.") }
                        .foregroundStyle(AppColors.accent)
                }
            }
            .padding(16)
        }
        .onAppear {
            guard !prompted else { return }
            prompted = true
            requestBiometric()
        }
    }

    private func requestBiometric() {
        vm.authenticateWithBiometrics(onSuccess: vm.unlockSavedLogin, onPassword: { vm.usePasswordLogin(message: "Please login with your password.") })
    }
}

struct AuthView: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var register = false
    @State private var username = ""
    @State private var password = ""
    @State private var fullName = ""

    var body: some View {
        ScrollView {
            SignalCard {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 12) {
                            AppBrandIcon(size: 56)
                            BrandHeader(subtitle: "Sign in to continue.")
                        }
                        Text(register ? "Create your SignalBridge account to start trading." : "Login with your SignalBridge credentials.")
                            .font(.footnote)
                            .foregroundStyle(AppColors.textSecondary)
                    }
                    VStack(spacing: 12) {
                        if register {
                            AuthTextField(title: "Full name", placeholder: "Your full name", text: $fullName)
                        }
                        AuthTextField(
                            title: "Username",
                            placeholder: "Enter your username",
                            text: $username,
                            autocapitalization: .never,
                            autocorrectionDisabled: true
                        )
                        AuthSecureField(title: "Password", placeholder: "Enter your password", text: $password)
                    }
                    ErrorText(text: vm.state.error)
                    PrimaryButton(title: register ? "Create account" : "Login") {
                        vm.login(username: username, password: password, register: register, fullName: fullName)
                    }
                    HStack {
                        Button(register ? "Use existing login" : "Register") { register.toggle() }
                        Spacer()
                    }
                    .font(.footnote)
                    .foregroundStyle(AppColors.accent)
                }
            }
            .padding(16)
            .frame(maxWidth: 460)
            .frame(maxWidth: .infinity)
        }
    }
}

struct FormTextField: View {
    let placeholder: String
    @Binding var text: String
    var keyboardType: UIKeyboardType = .default
    var autocapitalization: TextInputAutocapitalization = .sentences
    var disabled = false

    var body: some View {
        TextField(placeholder, text: $text)
            .foregroundStyle(AppColors.textPrimary)
            .tint(AppColors.accent)
            .keyboardType(keyboardType)
            .textInputAutocapitalization(autocapitalization)
            .disabled(disabled)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(AppColors.surfaceMuted)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

struct AuthTextField: View {
    let title: String
    let placeholder: String
    @Binding var text: String
    var autocapitalization: TextInputAutocapitalization = .words
    var autocorrectionDisabled = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppColors.textSecondary)
            TextField(placeholder, text: $text)
                .foregroundStyle(AppColors.textPrimary)
                .tint(AppColors.accent)
                .textInputAutocapitalization(autocapitalization)
                .autocorrectionDisabled(autocorrectionDisabled)
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(AppColors.surfaceMuted)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(AppColors.skyBorder)
                )
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }
}

struct AuthSecureField: View {
    let title: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppColors.textSecondary)
            SecureField(placeholder, text: $text)
                .foregroundStyle(AppColors.textPrimary)
                .tint(AppColors.accent)
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(AppColors.surfaceMuted)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(AppColors.skyBorder)
                )
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }
}

struct AppBrandIcon: View {
    var size: CGFloat = 56

    var body: some View {
        ZStack {
            Circle()
                .fill(LinearGradient(colors: [AppColors.accent.opacity(0.22), AppColors.sky.opacity(0.18)], startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: size * 1.08, height: size * 1.08)
                .blur(radius: size * 0.04)
            RoundedRectangle(cornerRadius: size * 0.32, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Color(hex: 0x0F172A), Color(hex: 0x312E81), Color(hex: 0x0284C7)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            RoundedRectangle(cornerRadius: size * 0.32, style: .continuous)
                .stroke(Color.white.opacity(0.18), lineWidth: 1)
            Image("BrandIcon")
                .resizable()
                .scaledToFit()
                .padding(size * 0.14)
        }
        .frame(width: size, height: size)
        .shadow(color: AppColors.cardShadow, radius: 10, y: 5)
    }
}

struct BrandHeader: View {
    let subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("SignalBridge")
                .font(.largeTitle.weight(.black))
                .foregroundStyle(AppColors.textPrimary)
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(AppColors.textSecondary)
        }
    }
}

struct SignalCard<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        VStack(alignment: .leading) { content }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppColors.surface)
            .clipShape(RoundedRectangle(cornerRadius: 24))
            .shadow(color: AppColors.cardShadow, radius: 8, y: 4)
    }
}

struct DataCard<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        VStack(alignment: .leading) { content }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppColors.surface)
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(AppColors.skyBorder.opacity(0.85)))
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .appCardShadow()
    }
}

struct PrimaryButton: View {
    let title: String
    var fullWidth = true
    var compact = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(compact ? .caption.weight(.semibold) : .body.weight(.semibold))
                .frame(maxWidth: fullWidth ? .infinity : nil)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(compact ? .small : .regular)
        .buttonBorderShape(compact ? .capsule : .roundedRectangle)
        .tint(AppColors.accent)
    }
}

struct SecondaryButton: View {
    let title: String
    var danger = false
    var compact = false
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .buttonStyle(.bordered)
            .controlSize(compact ? .small : .regular)
            .buttonBorderShape(compact ? .capsule : .roundedRectangle)
            .font(compact ? .caption.weight(.semibold) : .body.weight(.semibold))
            .tint(danger ? AppColors.danger : AppColors.accent)
    }
}

struct ErrorText: View {
    let text: String
    var body: some View {
        if !text.isEmpty {
            Text(text).font(.footnote.weight(.semibold)).foregroundStyle(AppColors.danger)
        }
    }
}

struct ErrorBanner: View {
    let text: String
    var body: some View {
        Text(text).font(.footnote).foregroundStyle(AppColors.danger)
            .padding(.horizontal, 12).padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppColors.dangerSoft)
            .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

struct EmptyText: View {
    let text: String
    var body: some View {
        DataCard {
            Text(text)
                .font(.subheadline)
                .foregroundStyle(AppColors.textSecondary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 8)
        }
    }
}

struct ScreenHeader: View {
    let title: String
    let subtitle: String
    var actionLabel: String?
    var onAction: (() -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 2)
                .fill(
                    LinearGradient(
                        colors: [AppColors.accent, AppColors.sky],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 4)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).appScreenTitle()
                if !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(AppColors.textSecondary)
                }
            }
            Spacer(minLength: 8)
            if let actionLabel, let onAction {
                Button(actionLabel, action: onAction)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(AppColors.accent)
                    .clipShape(Capsule())
            }
        }
        .padding(14)
        .background(
            LinearGradient(
                colors: [AppColors.surface, AppColors.skySoft.opacity(0.55)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(AppColors.skyBorder))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .appCardShadow()
    }
}

struct SummaryStrip: View {
    @EnvironmentObject private var vm: AppViewModel
    var body: some View {
        HStack(spacing: 8) {
            MetricPill(label: "P/L", value: formatMoney(vm.state.runningPl), positive: vm.state.runningPl >= 0, action: vm.openPositionsFromSummary)
            MetricPill(label: "Orders", value: "\(vm.state.orders.count)", positive: true, neutral: true, action: vm.openOrderHistoryFromSummary)
        }
    }
}

struct MetricPill: View {
    let label: String
    let value: String
    let positive: Bool
    var neutral = false
    var action: (() -> Void)? = nil

    var body: some View {
        Button(action: { action?() }) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label.uppercased())
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(AppColors.textMuted)
                Text(value)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(neutral ? AppColors.textPrimary : (positive ? AppColors.success : AppColors.danger))
            }
            .padding(.horizontal, 10).padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LinearGradient(
                    colors: [AppColors.surface, AppColors.skySoft.opacity(0.35)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.skyBorder.opacity(0.9)))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .disabled(action == nil)
    }
}

struct ChipRow: View {
    let values: [String]
    let selected: String
    let onSelect: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(values, id: \.self) { value in
                    Button(value) { onSelect(value) }
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 14).padding(.vertical, 7)
                        .background(value == selected ? AppColors.accent : AppColors.surface)
                        .foregroundStyle(value == selected ? .white : AppColors.textSecondary)
                        .overlay(
                            Capsule().stroke(value == selected ? AppColors.accent : AppColors.border, lineWidth: 1)
                        )
                        .clipShape(Capsule())
                        .shadow(color: value == selected ? AppColors.accent.opacity(0.2) : .clear, radius: 4, y: 2)
                }
            }
        }
    }
}

struct StatusPill: View {
    let label: String
    let positive: Bool
    var body: some View {
        Text(plainStatus(label))
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(positive ? AppColors.successSoft : AppColors.warningSoft)
            .foregroundStyle(positive ? AppColors.success : AppColors.warning)
            .clipShape(Capsule())
    }
}

struct StrategyStatusPill: View {
    let status: String
    var pulse = false

    private var normalized: String { status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }

    private var background: Color {
        switch normalized {
        case "armed": return AppColors.warningSoft
        case "long", "running": return AppColors.successSoft
        case "short", "error": return AppColors.dangerSoft
        case "reversing": return AppColors.accentSoft
        case "stopped": return AppColors.surfaceMuted
        default: return AppColors.surfaceMuted
        }
    }

    private var foreground: Color {
        switch normalized {
        case "armed": return AppColors.warning
        case "long", "running": return AppColors.success
        case "short", "error": return AppColors.danger
        case "reversing": return AppColors.accent
        case "stopped": return AppColors.textMuted
        default: return AppColors.textSecondary
        }
    }

    private var border: Color { foreground.opacity(0.35) }

    var body: some View {
        HStack(spacing: 5) {
            if pulse {
                Circle()
                    .fill(foreground.opacity(0.85))
                    .frame(width: 6, height: 6)
            }
            Text(normalized.replacingOccurrences(of: "_", with: " ").uppercased())
                .font(.system(size: 10, weight: .bold))
                .tracking(0.4)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(background)
        .foregroundStyle(foreground)
        .overlay(Capsule().stroke(border, lineWidth: 1))
        .clipShape(Capsule())
    }
}

struct TinyPill: View {
    let label: String
    let background: Color
    let foreground: Color
    var compact = false

    var body: some View {
        Text(label)
            .font(.system(size: compact ? 10 : 11, weight: .bold))
            .lineLimit(1)
            .padding(.horizontal, compact ? 7 : 9)
            .padding(.vertical, compact ? 4 : 5)
            .background(background)
            .foregroundStyle(foreground)
            .clipShape(Capsule())
    }
}

struct InstrumentBadge: View {
    let symbol: String

    var body: some View {
        if let flags = currencyFlags(symbol) {
            ZStack {
                Text(flags.0).font(.caption).offset(x: -6, y: -6)
                Text(flags.1).font(.caption).offset(x: 6, y: 6)
            }
            .frame(width: 38, height: 38)
            .background(AppColors.surface)
            .clipShape(Circle())
            .overlay(Circle().stroke(AppColors.border))
        } else {
            Text(badgeLabel)
                .font(.caption.weight(.black))
                .foregroundStyle(.white)
                .frame(width: 38, height: 38)
                .background(LinearGradient(colors: [Color(hex: 0x1E293B), AppColors.accent], startPoint: .topLeading, endPoint: .bottomTrailing))
                .clipShape(Circle())
        }
    }

    private var badgeLabel: String {
        let upper = symbol.uppercased()
        if upper.hasPrefix("XAU") { return "Au" }
        if upper.hasPrefix("XAG") { return "Ag" }
        return String(upper.prefix(3))
    }
}

struct PriceMovement: View {
    let price: Double?
    let direction: String
    var symbol: String? = nil
    var priceDigits: [String: Int] = [:]

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(formatPrice(price, symbol: symbol, priceDigits: priceDigits))
                .font(.subheadline.weight(.bold))
                .foregroundStyle(color)
            Text(directionLabel).font(.caption2.weight(.semibold)).foregroundStyle(color)
        }
        .frame(width: 108, alignment: .trailing)
    }

    private var color: Color {
        switch direction {
        case "up": return AppColors.success
        case "down": return AppColors.danger
        default: return AppColors.textSecondary
        }
    }

    private var directionLabel: String {
        switch direction {
        case "up": return "▲ Live"
        case "down": return "▼ Live"
        default: return "Live"
        }
    }
}

struct CompactToggle: View {
    let title: String
    let subtitle: String
    @Binding var checked: Bool

    var body: some View {
        Toggle(isOn: $checked) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(AppColors.textPrimary)
                Text(subtitle).font(.caption2).foregroundStyle(AppColors.textSecondary)
            }
        }
        .tint(AppColors.accent)
    }
}
