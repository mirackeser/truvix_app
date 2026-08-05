import PhotosUI
import SwiftUI

/// The new-analysis flow: four steps from an empty form to a finished report.
struct NewAnalysisView: View {
    @State private var model: NewAnalysisModel
    @Environment(\.dismiss) private var dismiss

    init(api: any TruvixAPI) {
        _model = State(wrappedValue: NewAnalysisModel(api: api))
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if model.step != .running {
                    StepIndicator(current: model.step)
                        .padding(.horizontal, Theme.Spacing.md)
                        .padding(.bottom, Theme.Spacing.md)
                }

                switch model.step {
                case .vehicleDetails:
                    VehicleDetailsStep(draft: model.draft, onContinue: model.advance)
                case .evidence:
                    EvidenceStep(model: model)
                case .review:
                    ReviewStep(model: model) {
                        Task { await model.submit() }
                    }
                case .running:
                    RunningStep(model: model) { dismiss() }
                }
            }
            .screenBackground()
            .navigationTitle("Yeni Analiz")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if model.step == .vehicleDetails || model.step == .running {
                        Button("Kapat") { dismiss() }
                            .foregroundStyle(Theme.Colours.textSecondary)
                            .disabled(model.isSubmitting)
                    } else {
                        Button {
                            model.goBack()
                        } label: {
                            Image(systemName: "chevron.left")
                        }
                        .foregroundStyle(Theme.Colours.textPrimary)
                    }
                }
            }
        }
    }
}

// MARK: - Step indicator

private struct StepIndicator: View {
    let current: AnalysisStep

    var body: some View {
        HStack(spacing: Theme.Spacing.xs) {
            ForEach(AnalysisStep.allCases) { step in
                let isDone = step.rawValue < current.rawValue
                let isCurrent = step == current

                ZStack {
                    Circle()
                        .fill(
                            isCurrent || isDone
                                ? AnyShapeStyle(Theme.Colours.brandGradient)
                                : AnyShapeStyle(Theme.Colours.surfaceElevated)
                        )
                        .frame(width: 28, height: 28)

                    if isDone {
                        Image(systemName: "checkmark")
                            .font(Theme.Typography.microBold)
                            .foregroundStyle(Theme.Colours.textOnBrand)
                    } else {
                        Text("\(step.rawValue)")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(
                                isCurrent
                                    ? Theme.Colours.textOnBrand
                                    : Theme.Colours.textSecondary
                            )
                    }
                }

                if step != AnalysisStep.allCases.last {
                    Rectangle()
                        .fill(isDone ? Theme.Colours.brand : Theme.Colours.surfaceElevated)
                        .frame(height: 2)
                        .frame(maxWidth: .infinity)
                }
            }
        }
        .animation(Theme.Motion.standard, value: current)
        .accessibilityElement()
        .accessibilityLabel("Adım \(current.rawValue) / \(AnalysisStep.allCases.count)")
    }
}

// MARK: - Step 1: vehicle details

private struct VehicleDetailsStep: View {
    @Bindable var draft: VehicleDraft
    let onContinue: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                Text("Aracın bilgilerini gir")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textPrimary)

                Text("Ne kadar çok bilgi verirsen analiz o kadar isabetli olur.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)

                Card {
                    VStack(spacing: Theme.Spacing.sm) {
                        TruvixTextField(
                            title: "Marka",
                            systemImage: "car",
                            text: $draft.make,
                            contentType: .organizationName
                        )
                        TruvixTextField(
                            title: "Model",
                            systemImage: "car.fill",
                            text: $draft.model
                        )
                        TruvixTextField(
                            title: "Donanım (isteğe bağlı)",
                            systemImage: "gearshape",
                            text: $draft.variant
                        )
                        TruvixTextField(
                            title: "Model yılı",
                            systemImage: "calendar",
                            text: $draft.modelYear,
                            keyboard: .numberPad
                        )
                        TruvixTextField(
                            title: "Kilometre",
                            systemImage: "speedometer",
                            text: $draft.mileageKm,
                            keyboard: .numberPad
                        )
                        TruvixTextField(
                            title: "İstenen fiyat (₺)",
                            systemImage: "turkishlirasign.circle",
                            text: $draft.price,
                            keyboard: .numberPad
                        )
                    }
                }

                Card {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        PickerRow(title: "Yakıt", selection: $draft.fuelType) { $0.displayName }
                        Divider().overlay(Theme.Colours.border)
                        PickerRow(title: "Vites", selection: $draft.transmission) { $0.displayName }
                        Divider().overlay(Theme.Colours.border)
                        OptionalBodyTypeRow(selection: $draft.bodyType)
                    }
                }

                Card {
                    VStack(spacing: Theme.Spacing.sm) {
                        TruvixTextField(
                            title: "Şehir (isteğe bağlı)",
                            systemImage: "mappin.and.ellipse",
                            text: $draft.city
                        )
                        TruvixTextField(
                            title: "Plaka (isteğe bağlı)",
                            systemImage: "rectangle.and.text.magnifyingglass",
                            text: $draft.plate,
                            keyboard: .asciiCapable
                        )
                        if draft.plateIsMalformed {
                            FieldHint(message: "Plaka '34 ABC 123' biçiminde olmalı.")
                        }

                        TruvixTextField(
                            title: "Şasi no / VIN (isteğe bağlı)",
                            systemImage: "number",
                            text: $draft.vin,
                            keyboard: .asciiCapable
                        )
                        if draft.vinIsMalformed {
                            FieldHint(message: "VIN 17 karakter olmalı; I, O ve Q içeremez.")
                        }
                    }
                }

                Button("Devam Et", action: onContinue)
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!draft.isComplete)
                    .opacity(draft.isComplete ? 1 : 0.5)
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .scrollDismissesKeyboard(.interactively)
    }
}

/// A labelled inline picker for an enumeration.
///
/// The display name is supplied by the caller rather than derived, because an
/// enum case's Swift name is an implementation detail and never the Turkish
/// label a reader should see.
private struct PickerRow<Value: CaseIterable & Hashable>: View {
    let title: String
    @Binding var selection: Value
    let displayName: (Value) -> String

    var body: some View {
        HStack {
            Text(title)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textSecondary)
            Spacer()
            Picker(title, selection: $selection) {
                ForEach(Array(Value.allCases), id: \.self) { option in
                    Text(displayName(option)).tag(option)
                }
            }
            .pickerStyle(.menu)
            .tint(Theme.Colours.brand)
        }
    }
}

/// Body type is optional, so it needs a "not specified" entry the enum lacks.
private struct OptionalBodyTypeRow: View {
    @Binding var selection: BodyType?

    var body: some View {
        HStack {
            Text("Kasa")
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textSecondary)
            Spacer()
            Picker("Kasa", selection: $selection) {
                Text("Belirtilmedi").tag(BodyType?.none)
                ForEach(BodyType.allCases, id: \.self) { option in
                    Text(option.displayName).tag(BodyType?.some(option))
                }
            }
            .pickerStyle(.menu)
            .tint(Theme.Colours.brand)
        }
    }
}

private struct FieldHint: View {
    let message: String

    var body: some View {
        Text(message)
            .font(Theme.Typography.caption)
            .foregroundStyle(Theme.Colours.warning)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Step 2: evidence

private struct EvidenceStep: View {
    @Bindable var model: NewAnalysisModel
    @State private var selection: [PhotosPickerItem] = []
    @State private var isImporting = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                Text("Fotoğrafları yükle")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textPrimary)

                Text("Motor, iç döşeme, gösterge, lastik ve hasarlı bölgeleri "
                    + "eklemeyi unutma. Ekspertiz raporunu PDF olarak da ekleyebilirsin.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                PhotosPicker(
                    selection: $selection,
                    maxSelectionCount: NewAnalysisModel.maximumUploads,
                    matching: .images
                ) {
                    HStack {
                        Image(systemName: "photo.badge.plus")
                        Text("Fotoğraf Ekle")
                    }
                }
                .buttonStyle(SecondaryButtonStyle())
                .disabled(!model.canAddMoreUploads || isImporting)

                if isImporting {
                    HStack(spacing: Theme.Spacing.xs) {
                        ProgressView().tint(Theme.Colours.brand)
                        Text("Fotoğraflar hazırlanıyor…")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }
                }

                if model.uploads.isEmpty {
                    Text("Henüz dosya eklenmedi. Fotoğrafsız da devam edebilirsin; "
                        + "analiz yalnızca girdiğin bilgilerle yapılır.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    ForEach($model.uploads) { $upload in
                        UploadRow(upload: $upload) { model.remove(upload) }
                    }

                    Text("\(model.uploads.count) / \(NewAnalysisModel.maximumUploads) dosya")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }

                Button("Devam Et", action: model.advance)
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(isImporting)
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .onChange(of: selection) { _, items in
            guard !items.isEmpty else { return }
            Task { await importSelection(items) }
        }
    }

    /// Load the chosen images into memory as JPEG data.
    ///
    /// Transferring here rather than at upload time means a failure to read a
    /// photo surfaces while the user is still on this screen, not midway
    /// through a run they cannot retry.
    private func importSelection(_ items: [PhotosPickerItem]) async {
        isImporting = true
        defer {
            isImporting = false
            selection = []
        }

        for item in items where model.canAddMoreUploads {
            guard let original = try? await item.loadTransferable(type: Data.self) else {
                continue
            }
            // Reduced before upload: a phone photograph is megabytes, and the
            // server reduces it again anyway before a model looks at it.
            guard let prepared = ImagePreparation.prepareForUpload(original) else { continue }

            model.add(
                PendingUpload(
                    data: prepared,
                    filename: "photo-\(model.uploads.count + 1).jpg",
                    contentType: "image/jpeg",
                    kind: .exterior
                )
            )
        }
    }
}

private struct UploadRow: View {
    @Binding var upload: PendingUpload
    let onRemove: () -> Void

    var body: some View {
        Card(padding: Theme.Spacing.sm) {
            HStack(spacing: Theme.Spacing.sm) {
                if let image = UIImage(data: upload.data) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 56, height: 56)
                        .clipShape(
                            RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        )
                } else {
                    Image(systemName: "doc")
                        .frame(width: 56, height: 56)
                        .background(Theme.Colours.surfaceElevated)
                        .clipShape(
                            RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        )
                }

                Picker("Tür", selection: $upload.kind) {
                    ForEach(PhotoKind.allCases, id: \.self) { kind in
                        Text(kind.displayName).tag(kind)
                    }
                }
                .pickerStyle(.menu)
                .tint(Theme.Colours.brand)

                Spacer(minLength: 0)

                Button(action: onRemove) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Bu dosyayı kaldır")
            }
        }
    }
}

// MARK: - Step 3: review

private struct ReviewStep: View {
    let model: NewAnalysisModel
    let onStart: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                Text("Bilgileri onayla")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textPrimary)

                Card {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                        SummaryRow(
                            label: "Araç",
                            value: [model.draft.trimmedMake, model.draft.trimmedModel]
                                .joined(separator: " ")
                        )
                        SummaryRow(label: "Model yılı", value: model.draft.modelYear)
                        SummaryRow(
                            label: "Kilometre",
                            value: model.draft.parsedMileage.map {
                                (NumberFormatter.turkishInteger
                                    .string(from: NSNumber(value: $0)) ?? "\($0)") + " km"
                            } ?? "—"
                        )
                        SummaryRow(label: "Yakıt", value: model.draft.fuelType.displayName)
                        SummaryRow(label: "Vites", value: model.draft.transmission.displayName)
                        SummaryRow(
                            label: "Fiyat",
                            value: model.draft.parsedPrice?.formatted(.TRY) ?? "—"
                        )
                        if let plate = model.draft.normalisedPlate {
                            SummaryRow(label: "Plaka", value: plate)
                        }
                        if model.draft.normalisedVIN != nil {
                            SummaryRow(label: "VIN", value: "Girildi")
                        }
                    }
                }

                Card {
                    HStack {
                        Image(systemName: "photo.stack")
                            .foregroundStyle(Theme.Colours.brand)
                        Text("\(model.uploads.count) dosya eklendi")
                            .font(Theme.Typography.callout)
                            .foregroundStyle(Theme.Colours.textPrimary)
                        Spacer()
                    }
                }

                if let message = model.errorMessage {
                    ErrorBanner(message: message)
                }

                Text("Truvix AI tüm verileri analiz ederek riskleri ve fiyat "
                    + "değerlendirmesini sunacaktır.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                Button("Analizi Başlat", action: onStart)
                    .buttonStyle(PrimaryButtonStyle(isLoading: model.isSubmitting))
                    .disabled(model.isSubmitting)
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
    }
}

private struct SummaryRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
            Spacer(minLength: Theme.Spacing.sm)
            Text(value)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textPrimary)
                .multilineTextAlignment(.trailing)
        }
    }
}

// MARK: - Step 4: running

private struct RunningStep: View {
    let model: NewAnalysisModel
    let onFinish: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.lg) {
                if let analysis = model.finishedAnalysis {
                    AnalysisReportContent(analysis: analysis)

                    if let message = model.errorMessage {
                        ErrorBanner(message: message)
                    }

                    Button("Bitir", action: onFinish)
                        .buttonStyle(PrimaryButtonStyle())
                } else {
                    Spacer(minLength: Theme.Spacing.xxl)

                    ZStack {
                        Circle()
                            .stroke(Theme.Colours.surfaceElevated, lineWidth: 6)
                            .frame(width: 128, height: 128)
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(Theme.Colours.brand)
                            .scaleEffect(1.6)
                    }

                    Text("Truvix AI Analiz Ediyor")
                        .font(Theme.Typography.title)
                        .foregroundStyle(Theme.Colours.textPrimary)

                    Text(model.progressCaption)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .multilineTextAlignment(.center)
                        .animation(Theme.Motion.quick, value: model.progressCaption)

                    Text("Lütfen bu ekranı kapatmayın.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
    }
}
