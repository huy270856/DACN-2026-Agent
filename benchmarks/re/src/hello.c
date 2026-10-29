/* SPDX-License-Identifier: MIT */
#include <windows.h>
__declspec(dllexport) __attribute__((noinline)) void emit_message(void) {
    const char text[] = "TUAN_RE_HELLO_v1\r\n";
    DWORD written;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text, sizeof(text)-1, &written, NULL);
}
int main(void) { emit_message(); return 0; }
