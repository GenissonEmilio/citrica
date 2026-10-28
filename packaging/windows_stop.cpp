// Standalone upgrade helper. Build x64 with MSVC /MT; no Python/Qt or external CRT.
// Never invoke the installed CLI, kill a target process, or display a dialog.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <bcrypt.h>
#include <pathcch.h>
#include <tlhelp32.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "pathcch.lib")

namespace {
struct Handle {
    HANDLE value = INVALID_HANDLE_VALUE;
    explicit Handle(HANDLE h = INVALID_HANDLE_VALUE) : value(h) {}
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    Handle(Handle&& other) noexcept : value(other.value) { other.value = INVALID_HANDLE_VALUE; }
};
[[noreturn]] void fail(const char* stage, DWORD error = GetLastError()) {
    throw std::runtime_error(std::string(stage) + " (Windows error " + std::to_string(error) + ")");
}
DWORD remaining(ULONGLONG deadline) {
    ULONGLONG now = GetTickCount64();
    return now < deadline ? static_cast<DWORD>(deadline - now) : 0;
}
std::wstring environment(const wchar_t* name) {
    DWORD size = GetEnvironmentVariableW(name, nullptr, 0);
    if (!size || size > 32768) fail("USERPROFILE is missing or invalid");
    std::wstring value(size, L'\0');
    DWORD read = GetEnvironmentVariableW(name, value.data(), size);
    if (!read || read >= size) fail("Cannot read USERPROFILE");
    value.resize(read);
    return value;
}
std::wstring pipe_name() {
    std::wstring profile = environment(L"USERPROFILE");
    std::replace(profile.begin(), profile.end(), L'/', L'\\');
    // Path.home()/PureWindowsPath drops a directory's trailing separator;
    // preserve the spelling/case and the separator of a drive root.
    std::vector<wchar_t> spelling(profile.begin(), profile.end());
    spelling.push_back(L'\0');
    while (PathCchRemoveBackslash(spelling.data(), spelling.size()) == S_OK) {}
    profile.assign(spelling.data());
    // PathCch regards a bare UNC share (\\server\share) as a root but
    // removes its final separator. PureWindowsPath includes that separator
    // in its UNC anchor, including when USERPROFILE omitted it originally.
    size_t unc_start = _wcsnicmp(profile.c_str(), L"\\\\?\\UNC\\", 8) == 0 ? 8 :
        (profile.rfind(L"\\\\", 0) == 0 ? 2 : std::wstring::npos);
    if (unc_start != std::wstring::npos && !profile.empty() && profile.back() != L'\\' &&
            PathCchIsRoot(profile.c_str())) {
        size_t server_end = profile.find(L'\\', unc_start);
        if (server_end != std::wstring::npos && server_end > unc_start && server_end + 1 < profile.size() &&
                profile.find(L'\\', server_end + 1) == std::wstring::npos) profile += L'\\';
    }
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, profile.data(),
        static_cast<int>(profile.size()), nullptr, 0, nullptr, nullptr);
    if (!size) fail("Cannot encode USERPROFILE as UTF-8");
    std::string utf8(size, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, profile.data(),
        static_cast<int>(profile.size()), utf8.data(), size, nullptr, nullptr)) fail("Cannot encode USERPROFILE");
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    unsigned char bytes[32] = {};
    NTSTATUS status = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0);
    if (status >= 0) status = BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0);
    if (status >= 0) status = BCryptHashData(hash, reinterpret_cast<PUCHAR>(utf8.data()), static_cast<ULONG>(size), 0);
    if (status >= 0) status = BCryptFinishHash(hash, bytes, static_cast<ULONG>(sizeof(bytes)), 0);
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    if (status < 0) fail("Cannot hash USERPROFILE", static_cast<DWORD>(status));
    const wchar_t hex[] = L"0123456789abcdef";
    std::wstring name = L"\\\\.\\pipe\\citrica-";
    for (unsigned index = 0; index < 10; ++index) {
        name += hex[bytes[index] >> 4];
        name += hex[bytes[index] & 15];
    }
    return name;
}
std::wstring normalized_path(std::wstring path) {
    std::replace(path.begin(), path.end(), L'/', L'\\');
    if (path.rfind(L"\\\\?\\UNC\\", 0) == 0) path = L"\\\\" + path.substr(8);
    else if (path.rfind(L"\\\\?\\", 0) == 0) path = path.substr(4);
    std::vector<wchar_t> full(32768);
    DWORD length = GetFullPathNameW(path.c_str(), static_cast<DWORD>(full.size()), full.data(), nullptr);
    if (!length || length >= full.size()) fail("Cannot resolve installation path");
    std::wstring result(full.data(), length);
    Handle file(CreateFileW(result.c_str(), FILE_READ_ATTRIBUTES,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, 0, nullptr));
    if (file.value != INVALID_HANDLE_VALUE) {
        length = GetFinalPathNameByHandleW(file.value, full.data(), static_cast<DWORD>(full.size()), FILE_NAME_NORMALIZED);
        if (!length || length >= full.size()) fail("Cannot resolve executable identity");
        result.assign(full.data(), length);
        if (result.rfind(L"\\\\?\\UNC\\", 0) == 0) result = L"\\\\" + result.substr(8);
        else if (result.rfind(L"\\\\?\\", 0) == 0) result = result.substr(4);
    } else if (GetLastError() != ERROR_FILE_NOT_FOUND && GetLastError() != ERROR_PATH_NOT_FOUND) {
        fail("Cannot inspect executable path");
    }
    return result;
}
bool same_path(const std::wstring& first, const std::wstring& second) {
    return CompareStringOrdinal(first.c_str(), -1, second.c_str(), -1, TRUE) == CSTR_EQUAL;
}
std::wstring process_path(HANDLE process) {
    std::vector<wchar_t> path(32768);
    DWORD size = static_cast<DWORD>(path.size());
    if (!QueryFullProcessImageNameW(process, 0, path.data(), &size)) fail("Cannot inspect Cítrica process");
    return normalized_path(std::wstring(path.data(), size));
}
std::vector<Handle> matching_processes(const std::wstring& executable) {
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0));
    if (snapshot.value == INVALID_HANDLE_VALUE) fail("Cannot enumerate processes");
    PROCESSENTRY32W entry = {};
    entry.dwSize = sizeof(entry);
    std::vector<Handle> matches;
    if (!Process32FirstW(snapshot.value, &entry)) fail("Cannot enumerate first process");
    do {
        if (_wcsicmp(entry.szExeFile, L"Citrica.exe") != 0) continue;
        Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, entry.th32ProcessID));
        if (!process.value) {
            if (GetLastError() == ERROR_INVALID_PARAMETER) continue; // Exited during enumeration.
            fail("Cannot open Cítrica process for inspection");
        }
        if (WaitForSingleObject(process.value, 0) == WAIT_OBJECT_0) continue;
        if (same_path(process_path(process.value), executable)) matches.emplace_back(std::move(process));
    } while (Process32NextW(snapshot.value, &entry));
    if (GetLastError() != ERROR_NO_MORE_FILES) fail("Process enumeration failed");
    return matches;
}
struct Io {
    OVERLAPPED overlapped = {};
    char buffer[4096] = {};
    Io() {
        overlapped.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!overlapped.hEvent) fail("Cannot create pipe I/O event");
    }
    ~Io() { CloseHandle(overlapped.hEvent); }
};
DWORD transfer(HANDLE pipe, Io& operation, bool write, DWORD amount, ULONGLONG deadline,
               bool& still_pending) {
    BOOL completed = write ? WriteFile(pipe, operation.buffer, amount, nullptr, &operation.overlapped) :
                             ReadFile(pipe, operation.buffer, amount, nullptr, &operation.overlapped);
    if (!completed && GetLastError() != ERROR_IO_PENDING) fail(write ? "Cannot send quit request" : "Cannot read quit response");
    if (!completed) {
        still_pending = true;
        DWORD wait = WaitForSingleObject(operation.overlapped.hEvent, remaining(deadline));
        if (wait != WAIT_OBJECT_0) {
            CancelIoEx(pipe, &operation.overlapped);
            if (WaitForSingleObject(operation.overlapped.hEvent, 0) == WAIT_OBJECT_0) still_pending = false;
            fail(wait == WAIT_TIMEOUT ? "Quit pipe I/O deadline exceeded" : "Quit pipe wait failed",
                 wait == WAIT_TIMEOUT ? ERROR_TIMEOUT : GetLastError());
        }
        still_pending = false;
    }
    DWORD bytes = 0;
    if (!GetOverlappedResult(pipe, &operation.overlapped, &bytes, FALSE)) fail("Quit pipe I/O failed");
    return bytes;
}
DWORD exchange(HANDLE pipe, bool write, std::string& value, ULONGLONG deadline) {
    auto operation = std::make_unique<Io>();
    bool pending = false;
    DWORD length = write ? static_cast<DWORD>(value.size()) : static_cast<DWORD>(sizeof(operation->buffer));
    if (write) memcpy(operation->buffer, value.data(), length);
    try {
        DWORD bytes = transfer(pipe, *operation, write, length, deadline, pending);
        if (!write) value.assign(operation->buffer, bytes);
        return bytes;
    } catch (...) {
        // CancelIoEx is asynchronous. On a deadline do not free an OVERLAPPED
        // or buffer still owned by Windows. The one-shot helper exits shortly;
        // the OS reclaims this allocation/event when the helper process exits.
        if (pending) operation.release();
        throw;
    }
}
bool acknowledged(const std::string& text) {
    const char* cursor = text.c_str();
    const auto space = [&]() { while (*cursor && strchr(" \t\r\n", *cursor)) ++cursor; };
    const char* parts[] = {"{", "\"ok\"", ":", "true", "}"};
    for (const char* part : parts) {
        space();
        size_t size = strlen(part);
        if (strncmp(cursor, part, size) != 0) return false;
        cursor += size;
    }
    space();
    return !*cursor;
}
void request_quit(const std::wstring& name, const std::wstring& executable, ULONGLONG deadline) {
    Handle pipe;
    while (remaining(deadline)) {
        pipe.value = CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                                 OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr);
        if (pipe.value != INVALID_HANDLE_VALUE) break;
        DWORD error = GetLastError();
        if (error != ERROR_PIPE_BUSY) fail("Cítrica quit pipe is unavailable", error);
        DWORD wait_ms = remaining(deadline);
        if (!wait_ms) break;
        if (!WaitNamedPipeW(name.c_str(), std::min<DWORD>(wait_ms, 200))) {
            if (GetLastError() != ERROR_SEM_TIMEOUT) fail("Cannot connect to Cítrica quit pipe");
        }
    }
    if (pipe.value == INVALID_HANDLE_VALUE) fail("Quit pipe connection deadline exceeded", ERROR_TIMEOUT);
    ULONG owner = 0;
    if (!GetNamedPipeServerProcessId(pipe.value, &owner)) fail("Cannot identify quit pipe owner");
    Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, owner));
    if (!process.value || !same_path(process_path(process.value), executable))
        fail("Quit pipe belongs to another installation", ERROR_ACCESS_DENIED);
    std::string request = "{\"op\":\"quit\"}\n";
    if (exchange(pipe.value, true, request, deadline) != request.size()) fail("Incomplete quit request", ERROR_WRITE_FAULT);
    std::string response, chunk;
    while (response.find('\n') == std::string::npos) {
        if (!exchange(pipe.value, false, chunk, deadline)) fail("Quit pipe closed before acknowledgement", ERROR_BROKEN_PIPE);
        response += chunk;
        if (response.size() > 4096) fail("Invalid quit acknowledgement", ERROR_INVALID_DATA);
    }
    if (!acknowledged(response.substr(0, response.find('\n')))) fail("Cítrica rejected quit request", ERROR_INVALID_DATA);
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
    try {
        std::wstring directory;
        DWORD timeout = 15000;
        if (argc == 2 && wcscmp(argv[1], L"--pipe-name") == 0) {
            std::fwprintf(stdout, L"%ls\n", pipe_name().c_str());
            return 0;
        }
        for (int index = 1; index < argc; ++index) {
            if (wcscmp(argv[index], L"--install-dir") == 0 && index + 1 < argc) directory = argv[++index];
            else if (wcscmp(argv[index], L"--timeout-ms") == 0 && index + 1 < argc) {
                wchar_t* end = nullptr;
                unsigned long value = wcstoul(argv[++index], &end, 10);
                if (!*argv[index] || !end || *end || value < 100 || value > 15000) throw std::runtime_error("Timeout must be 100..15000 ms");
                timeout = static_cast<DWORD>(value);
            } else throw std::runtime_error("Usage: citrica-stop.exe --install-dir <directory> [--timeout-ms 15000]");
        }
        if (directory.empty()) throw std::runtime_error("An explicit installation directory is required");
        ULONGLONG deadline = GetTickCount64() + timeout;
        std::wstring executable = normalized_path(directory + L"\\Citrica.exe");
        auto processes = matching_processes(executable);
        if (processes.empty()) return 0;
        std::string error;
        try {
            request_quit(pipe_name(), executable, GetTickCount64() + std::min<DWORD>(5000, remaining(deadline)));
        } catch (const std::exception& exception) {
            error = exception.what(); // Process exit itself is authoritative if an acknowledgement races shutdown.
        }
        for (const auto& process : processes) {
            if (WaitForSingleObject(process.value, remaining(deadline)) != WAIT_OBJECT_0) {
                throw std::runtime_error(error.empty() ? "Cítrica did not stop within the deadline; close it from its tray" : error);
            }
        }
        if (!matching_processes(executable).empty()) throw std::runtime_error("Another Cítrica instance still uses the installation directory");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "Citrica stop helper: %s\n", error.what());
        return 1;
    } catch (...) {
        std::fputs("Citrica stop helper: unexpected failure\n", stderr);
        return 1;
    }
}
