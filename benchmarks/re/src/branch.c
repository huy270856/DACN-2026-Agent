/* SPDX-License-Identifier: MIT */
#include <windows.h>
__declspec(dllexport) __attribute__((noinline)) int classify_value(int value) {
    if (value < 0) return -1;
    if (value == 0) return 0;
    return 1;
}
int main(void) {
    const char text[] = "TUAN_RE_BRANCH_v1\r\n";
    volatile int input = 7;
    DWORD written;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text, sizeof(text)-1, &written, NULL);
    return classify_value(input) == 1 ? 0 : 1;
}
