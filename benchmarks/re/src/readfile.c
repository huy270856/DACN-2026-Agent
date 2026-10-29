/* SPDX-License-Identifier: MIT */
#include <windows.h>
__declspec(dllexport) __attribute__((noinline)) int read_fixture(void) {
    char buffer[64]; DWORD count;
    HANDLE file = CreateFileA("fixture.txt", GENERIC_READ, FILE_SHARE_READ, NULL,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 2;
    BOOL ok = ReadFile(file, buffer, sizeof(buffer), &count, NULL);
    CloseHandle(file);
    return ok ? 0 : 3;
}
int main(void) {
    const char text[] = "TUAN_RE_READFILE_v1\r\n"; DWORD written;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text, sizeof(text)-1, &written, NULL);
    return read_fixture();
}
