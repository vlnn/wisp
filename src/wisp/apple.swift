import Foundation
#if canImport(FoundationModels)
import FoundationModels
#endif

@main
struct Main {
    static func main() async {
        #if canImport(FoundationModels)
        guard #available(macOS 26, *) else {
            fail("Apple Intelligence needs macOS 26 or later", 2)
        }
        let instructions = CommandLine.arguments.dropFirst().first ?? ""
        let prompt = String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self)
        let model = SystemLanguageModel.default
        guard case .available = model.availability else {
            fail("Apple Intelligence is not available: \(model.availability)", 2)
        }
        let session = LanguageModelSession(model: model, instructions: instructions)
        do {
            for try await snapshot in session.streamResponse(to: prompt) {
                emit(snapshot.content)
            }
        } catch {
            fail("\(error)", 1)
        }
        #else
        fail("This Mac's SDK has no FoundationModels framework; macOS 26 is needed", 2)
        #endif
    }

    static func emit(_ text: String) {
        guard let line = try? JSONEncoder().encode(text) else { return }
        FileHandle.standardOutput.write(line + Data("\n".utf8))
    }

    static func fail(_ message: String, _ code: Int32) -> Never {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        exit(code)
    }
}
