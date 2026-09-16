import SwiftUI
import UIKit

enum AppColors {
    static let background = adaptiveColor(light: 0xF0F9FF, dark: 0x020617)
    static let backgroundBottom = adaptiveColor(light: 0xEEF2FF, dark: 0x111827)
    static let surface = adaptiveColor(light: 0xFFFFFF, dark: 0x0F172A)
    static let surfaceMuted = adaptiveColor(light: 0xF8FAFC, dark: 0x172033)
    static let border = adaptiveColor(light: 0xE2E8F0, dark: 0x334155)
    static let skySoft = adaptiveColor(light: 0xE0F2FE, dark: 0x082F49)
    static let skyBorder = adaptiveColor(light: 0xBAE6FD, dark: 0x0EA5E9)
    static let sky = adaptiveColor(light: 0x0284C7, dark: 0x38BDF8)
    static let skyDeep = adaptiveColor(light: 0x0369A1, dark: 0x7DD3FC)
    static let textPrimary = adaptiveColor(light: 0x0F172A, dark: 0xE5EEF9)
    static let textSecondary = adaptiveColor(light: 0x475569, dark: 0xBFDBFE)
    static let textMuted = adaptiveColor(light: 0x64748B, dark: 0x94A3B8)
    static let accent = adaptiveColor(light: 0x4F46E5, dark: 0xA5B4FC)
    static let accentDeep = adaptiveColor(light: 0x3730A3, dark: 0xC7D2FE)
    static let accentSoft = adaptiveColor(light: 0xEEF2FF, dark: 0x1E1B4B)
    static let danger = adaptiveColor(light: 0xE11D48, dark: 0xFB7185)
    static let dangerSoft = adaptiveColor(light: 0xFFF1F2, dark: 0x4C0519)
    static let success = adaptiveColor(light: 0x059669, dark: 0x34D399)
    static let successSoft = adaptiveColor(light: 0xECFDF5, dark: 0x052E2B)
    static let warning = adaptiveColor(light: 0xB45309, dark: 0xFBBF24)
    static let warningSoft = adaptiveColor(light: 0xFFFBEB, dark: 0x422006)
    static let trap = adaptiveColor(light: 0x6D28D9, dark: 0xC4B5FD)
    static let trapSoft = adaptiveColor(light: 0xEDE9FE, dark: 0x2E1065)
    static let cardShadow = adaptiveColor(light: 0x1E3A8A, dark: 0x020617, lightAlpha: 0.08, darkAlpha: 0.36)
}

enum LoaderColors {
    static let background = Color(hex: 0x0B1220)
    static let surface = Color(hex: 0x151F33)
    static let accent = Color(hex: 0x818CF8)
    static let accentGlow = Color(hex: 0x6366F1)
    static let text = Color(hex: 0xE2E8F0)
    static let muted = Color(hex: 0x94A3B8)
}

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}

private func adaptiveColor(light: UInt32, dark: UInt32, lightAlpha: Double = 1, darkAlpha: Double = 1) -> Color {
    Color(
        uiColor: UIColor { traits in
            if traits.userInterfaceStyle == .dark {
                return uiColor(hex: dark, alpha: darkAlpha)
            }
            return uiColor(hex: light, alpha: lightAlpha)
        }
    )
}

private func uiColor(hex: UInt32, alpha: Double = 1) -> UIColor {
    UIColor(
        red: CGFloat(Double((hex >> 16) & 0xFF) / 255),
        green: CGFloat(Double((hex >> 8) & 0xFF) / 255),
        blue: CGFloat(Double(hex & 0xFF) / 255),
        alpha: alpha
    )
}

extension View {
    func appScreenTitle() -> some View {
        font(.title2.weight(.bold))
            .foregroundStyle(AppColors.textPrimary)
    }

    func appHeadline() -> some View {
        font(.headline.weight(.semibold))
            .foregroundStyle(AppColors.textPrimary)
    }

    func appSectionLabel() -> some View {
        font(.caption.weight(.bold))
            .tracking(0.7)
            .foregroundStyle(AppColors.skyDeep)
    }

    func appCardShadow() -> some View {
        shadow(color: AppColors.cardShadow, radius: 10, y: 4)
    }
}
