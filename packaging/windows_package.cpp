// MSIX-only bridge: /MT, Windows SDK WinRT, no Python/Qt or external CRT.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <appmodel.h>
#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Storage.h>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
using winrt::Windows::ApplicationModel::StartupTask;
using winrt::Windows::ApplicationModel::StartupTaskState;
using Clock = std::chrono::steady_clock;

std::string quote(const std::string& value) {
    std::string result = "\"";
    const char* hex = "0123456789abcdef";
    for (char raw : value) {
        unsigned char character = static_cast<unsigned char>(raw);
        if (character == '"' || character == '\\') { result += '\\'; result += raw; }
        else if (character < 32) {
            result += "\\u00";
            result += hex[character >> 4];
            result += hex[character & 15];
        } else result += raw;
    }
    return result + '"';
}
void emit(const std::string& value) {
    std::fwrite(value.data(), 1, value.size(), stdout);
    std::fputc('\n', stdout);
    std::fflush(stdout);
}
std::string family_name() {
    UINT32 size = 0;
    LONG status = GetCurrentPackageFamilyName(&size, nullptr);
    if (status != ERROR_INSUFFICIENT_BUFFER) {
        winrt::throw_hresult(status == ERROR_SUCCESS ? E_UNEXPECTED : HRESULT_FROM_WIN32(status));
    }
    std::vector<wchar_t> family(size);
    winrt::check_win32(GetCurrentPackageFamilyName(&size, family.data()));
    return winrt::to_string(std::wstring_view(family.data()));
}
void require_desktop_context() {
    HANDLE token = nullptr;
    winrt::check_bool(OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token));
    DWORD app_container = 0, size = 0;
    BOOL read = GetTokenInformation(token, TokenIsAppContainer, &app_container, static_cast<DWORD>(sizeof(app_container)), &size);
    DWORD error = read ? ERROR_SUCCESS : GetLastError();
    CloseHandle(token);
    winrt::check_win32(error);
    // Desktop StartupTask requests have no consent UI. Reject AppContainer
    // execution rather than triggering its different consent-dialog contract.
    if (app_container) winrt::throw_hresult(E_ACCESSDENIED);
}
template<typename Operation>
auto complete(const Operation& operation, Clock::time_point deadline) {
    auto remaining = deadline - Clock::now();
    if (remaining <= Clock::duration::zero() ||
            operation.wait_for(std::chrono::duration_cast<std::chrono::milliseconds>(remaining)) == winrt::Windows::Foundation::AsyncStatus::Started) {
        operation.Cancel();
        winrt::throw_hresult(HRESULT_FROM_WIN32(ERROR_TIMEOUT));
    }
    return operation.GetResults();
}
const char* state_name(StartupTaskState state) {
    switch (state) {
    case StartupTaskState::Disabled: return "Disabled";
    case StartupTaskState::DisabledByUser: return "DisabledByUser";
    case StartupTaskState::Enabled: return "Enabled";
    case StartupTaskState::DisabledByPolicy: return "DisabledByPolicy";
    case StartupTaskState::EnabledByPolicy: return "EnabledByPolicy";
    default: winrt::throw_hresult(E_UNEXPECTED);
    }
}
std::string startup(const std::wstring& action) {
    if (action != L"query" && action != L"enable" && action != L"disable")
        throw std::runtime_error("Startup action must be query, enable or disable.");
    auto deadline = Clock::now() + std::chrono::seconds(6);
    auto task = complete(StartupTask::GetAsync(L"CitricaStartup"), deadline);
    auto before = task.State(), state = before;
    // User/policy decisions are never overridden. In particular never call
    // RequestEnableAsync for DisabledByUser, DisabledByPolicy or EnabledByPolicy.
    if (action == L"enable" && before == StartupTaskState::Disabled)
        state = complete(task.RequestEnableAsync(), deadline);
    else if (action == L"disable" && before == StartupTaskState::Enabled) {
        task.Disable();
        state = task.State();
    }
    bool enabled = state == StartupTaskState::Enabled || state == StartupTaskState::EnabledByPolicy;
    bool blocked = state == StartupTaskState::DisabledByUser || state == StartupTaskState::DisabledByPolicy ||
                   state == StartupTaskState::EnabledByPolicy;
    return ",\"task_id\":\"CitricaStartup\",\"state\":" + quote(state_name(state)) +
        ",\"enabled\":" + (enabled ? "true" : "false") + ",\"blocked\":" + (blocked ? "true" : "false") +
        ",\"changed\":" + (state != before ? "true" : "false");
}
int failure(const std::string& message, HRESULT code) {
    char hresult[16] = {};
    std::snprintf(hresult, sizeof(hresult), "0x%08lX", static_cast<unsigned long>(code));
    emit("{\"ok\":false,\"error\":" + quote(message) + ",\"hresult\":" + quote(hresult) + "}");
    std::fprintf(stderr, "Citrica MSIX helper: %s\n", message.c_str());
    return 1;
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
    try {
        winrt::init_apartment(winrt::apartment_type::multi_threaded);
        std::string family = family_name();
        require_desktop_context();
        std::string details;
        if (argc == 2 && wcscmp(argv[1], L"--paths") == 0) {
            auto data = winrt::Windows::Storage::ApplicationData::Current();
            details = ",\"local_folder\":" + quote(winrt::to_string(data.LocalFolder().Path())) +
                      ",\"local_cache\":" + quote(winrt::to_string(data.LocalCacheFolder().Path())) +
                      ",\"temporary_folder\":" + quote(winrt::to_string(data.TemporaryFolder().Path()));
        } else if (argc == 3 && wcscmp(argv[1], L"--startup") == 0) {
            details = startup(argv[2]);
        } else throw std::runtime_error("Usage: citrica-package.exe --paths | --startup query|enable|disable");
        emit("{\"ok\":true,\"package_family\":" + quote(family) + details + "}");
        return 0;
    } catch (const winrt::hresult_error& error) {
        return failure(winrt::to_string(error.message()), error.code());
    } catch (const std::exception& error) {
        return failure(error.what(), E_FAIL);
    } catch (...) {
        return failure("Unexpected package helper failure.", E_FAIL);
    }
}
