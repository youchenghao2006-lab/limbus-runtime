import SwiftUI
import AppKit

struct RuntimeStatus: Decodable {
    var runtimeReady = false
    var steamInstalled = false
    var gameState = "missing"
    var engine = "Wine 11 · Sikarugir"
    var renderer = "Apple D3DMetal"
    var root = ""
    var compatibility = "experimental"
}

struct ActionResult: Decodable {
    var ok: Bool
    var message: String
}

enum LauncherError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        switch self { case .message(let value): return value }
    }
}

@MainActor
final class LauncherModel: ObservableObject {
    @Published var state = RuntimeStatus()
    @Published var busy = false
    @Published var message = "正在检查本机环境…"
    @Published var error = false
    let root: URL
    let backend: URL

    init() {
        let resources = Bundle.main.resourceURL!
        backend = resources.appendingPathComponent("backend.py")
        if let path = ProcessInfo.processInfo.environment["LIMBUS_RUNTIME_HOME"], !path.isEmpty {
            root = URL(fileURLWithPath: (path as NSString).expandingTildeInPath, isDirectory: true)
                .standardizedFileURL.resolvingSymlinksInPath()
        } else {
            root = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/Limbus Runtime", isDirectory: true)
        }
    }

    nonisolated static func invoke(backend: URL, root: URL, action: String) throws -> Data {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: "/usr/bin/python3") else {
            throw LauncherError.message("缺少 Python 3，请按 README 安装 Apple Command Line Tools。")
        }
        process.arguments = [backend.path, "--root", root.path, action]
        let output = Pipe()
        process.standardOutput = output
        // Diagnostics remain local; no Steam credentials/config files are read.
        process.standardError = FileHandle.nullDevice
        try process.run()
        let deadline = Date().addingTimeInterval(20)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.1)
        }
        if process.isRunning {
            process.terminate()
            throw LauncherError.message("操作超时，请查看日志后重试。")
        }
        return output.fileHandleForReading.readDataToEndOfFile()
    }

    func refresh() async {
        let backend = backend, root = root
        do {
            let data = try await Task.detached {
                try Self.invoke(backend: backend, root: root, action: "status")
            }.value
            state = try JSONDecoder().decode(RuntimeStatus.self, from: data)
            if message == "正在检查本机环境…" || message.hasPrefix("运行环境尚未初始化") {
                if !state.runtimeReady {
                    message = "运行环境尚未初始化。请按 README 执行 scripts/prepare_runtime.py，再刷新状态。"
                } else if state.gameState == "installed" {
                    message = "游戏已就绪。可直接启动，后续更新由 Steam 完成。"
                } else if state.gameState == "downloading" {
                    message = "游戏正在准备中，请在 Steam 中查看下载进度。"
                } else {
                    message = state.steamInstalled ? "环境已就绪。打开 Steam 登录，然后安装游戏。" : "请先安装 Steam。"
                }
            }
        } catch {
            self.error = true
            message = "无法读取环境状态：\(error.localizedDescription)"
        }
    }

    func perform(_ action: String) {
        guard !busy else { return }
        busy = true
        error = false
        message = "正在处理…"
        let backend = backend, root = root
        Task {
            do {
                let data = try await Task.detached {
                    try Self.invoke(backend: backend, root: root, action: action)
                }.value
                let result = try JSONDecoder().decode(ActionResult.self, from: data)
                message = result.message
                error = !result.ok
            } catch {
                self.error = true
                message = error.localizedDescription
            }
            busy = false
            await refresh()
        }
    }

    func showLogs() {
        NSWorkspace.shared.open(root.appendingPathComponent("logs", isDirectory: true))
    }
}

struct ClockMark: View {
    var body: some View {
        ZStack {
            Circle().stroke(Color(red: 0.86, green: 0.35, blue: 0.25), lineWidth: 2)
            Circle().stroke(.white.opacity(0.12), lineWidth: 1).padding(7)
            Rectangle().fill(.white.opacity(0.88)).frame(width: 2, height: 20).offset(y: -9)
            Rectangle().fill(Color(red: 0.86, green: 0.35, blue: 0.25)).frame(width: 18, height: 2).offset(x: 8)
            Circle().fill(.white).frame(width: 5, height: 5)
        }.frame(width: 60, height: 60)
    }
}

struct LauncherView: View {
    @StateObject private var model = LauncherModel()
    @State private var showRepair = false
    @State private var showStop = false
    private let cream = Color(red: 0.91, green: 0.87, blue: 0.79)
    private let accent = Color(red: 0.81, green: 0.28, blue: 0.20)

    var gameText: String {
        switch model.state.gameState {
        case "installed": return "已安装"
        case "downloading": return "下载或更新中"
        case "unknown": return "待检查"
        default: return "尚未安装"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 25) {
            HStack(alignment: .center, spacing: 18) {
                ClockMark()
                VStack(alignment: .leading, spacing: 5) {
                    Text("LIMBUS / COMMUNITY LAUNCHER").font(.system(size: 10, weight: .medium, design: .monospaced)).tracking(2).foregroundStyle(cream.opacity(0.5))
                    Text("Limbus Runtime").font(.system(size: 28, weight: .semibold)).foregroundStyle(cream)
                }
                Spacer()
                Text("实验版 0.2.0").font(.system(size: 11, design: .monospaced)).foregroundStyle(cream.opacity(0.5))
            }
            Rectangle().fill(cream.opacity(0.15)).frame(height: 1)
            HStack(spacing: 15) {
                statusCard("运行环境", value: model.state.runtimeReady ? "已准备好" : "未就绪", ready: model.state.runtimeReady)
                statusCard("Steam", value: model.state.steamInstalled ? "已安装" : "尚未安装", ready: model.state.steamInstalled)
                statusCard("边狱巴士", value: gameText, ready: model.state.gameState == "installed")
            }
            VStack(alignment: .leading, spacing: 13) {
                Text(model.state.gameState == "installed" ? "下一站，金枝。" : "准备出发。").font(.system(size: 25, weight: .medium)).foregroundStyle(cream)
                Text(model.state.gameState == "installed" ? "请用下方按钮启动游戏，以保持正确的画面设置。Steam 负责登录和更新。" : "首次使用先在 Steam 窗口登录，再安装《Limbus Company》。")
                    .font(.system(size: 13)).foregroundStyle(cream.opacity(0.63))
                HStack(spacing: 12) {
                    Button {
                        model.perform(model.state.gameState == "installed" ? "launch-game" : "install-game")
                    } label: {
                        Label(model.state.gameState == "installed" ? "启动游戏" : "安装游戏", systemImage: "play.fill")
                            .font(.system(size: 14, weight: .semibold)).frame(width: 170, height: 43)
                    }
                    .buttonStyle(.plain).background(accent, in: RoundedRectangle(cornerRadius: 7)).foregroundStyle(.white)
                    .disabled(model.busy || !model.state.runtimeReady || !model.state.steamInstalled)
                    Button(model.state.steamInstalled ? "打开 Steam" : "安装 Steam") {
                        model.perform(model.state.steamInstalled ? "open-steam" : "install-steam")
                    }
                    .buttonStyle(.plain).font(.system(size: 13)).padding(.horizontal, 20).frame(height: 43)
                    .background(cream.opacity(0.07), in: RoundedRectangle(cornerRadius: 7)).foregroundStyle(cream)
                    .disabled(model.busy || !model.state.runtimeReady)
                    if model.busy { ProgressView().controlSize(.small).padding(.leading, 5) }
                }.padding(.top, 4)
            }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
                .background(cream.opacity(0.035), in: RoundedRectangle(cornerRadius: 10))
            HStack(alignment: .top, spacing: 9) {
                Image(systemName: model.error ? "exclamationmark.circle" : "info.circle").padding(.top, 1)
                Text(model.message).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }.font(.system(size: 12)).foregroundStyle(model.error ? Color.orange : cream.opacity(0.65)).frame(minHeight: 32, alignment: .topLeading)
            Spacer(minLength: 0)
            HStack {
                Text("实验版 · 游戏兼容性待验证").foregroundStyle(cream.opacity(0.45))
                Spacer()
                Button("刷新状态") { Task { await model.refresh() } }
                Button("查看日志") { model.showLogs() }
                Button("修复环境") { showRepair = true }.disabled(model.busy || !model.state.runtimeReady)
                Button("停止环境") { showStop = true }.disabled(model.busy || !model.state.runtimeReady)
            }.font(.system(size: 11)).buttonStyle(.plain).foregroundStyle(cream.opacity(0.7))
        }
        .padding(32).frame(minWidth: 740, idealWidth: 780, minHeight: 535, idealHeight: 560)
        .background(Color(red: 0.075, green: 0.078, blue: 0.085))
        .preferredColorScheme(.dark)
        .confirmationDialog("刷新运行环境", isPresented: $showRepair, titleVisibility: .visible) {
            Button("刷新环境") { model.perform("repair") }
        } message: { Text("请先退出游戏。此操作刷新系统组件，保留已安装游戏和存档。") }
        .confirmationDialog("停止运行环境", isPresented: $showStop, titleVisibility: .visible) {
            Button("关闭本环境中的 Steam 和游戏", role: .destructive) { model.perform("stop") }
        } message: { Text("请先保存游戏进度。其他 Steam 和 CrossOver 环境不受影响。") }
        .task {
            while !Task.isCancelled {
                await model.refresh()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    private func statusCard(_ title: String, value: String, ready: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(.system(size: 11)).foregroundStyle(cream.opacity(0.5))
            HStack(spacing: 7) {
                Circle().fill(ready ? Color(red: 0.53, green: 0.68, blue: 0.48) : cream.opacity(0.25)).frame(width: 5, height: 5)
                Text(value).font(.system(size: 15, weight: .medium)).foregroundStyle(cream)
            }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(cream.opacity(0.045), in: RoundedRectangle(cornerRadius: 8))
    }
}

@main
struct LimbusLauncherApp: App {
    var body: some Scene {
        WindowGroup("Limbus Runtime") { LauncherView() }
            .windowStyle(.hiddenTitleBar)
            .windowResizability(.contentMinSize)
            .defaultSize(width: 780, height: 560)
    }
}
