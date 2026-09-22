#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#define ACCEPTANCE_INPUTS 6U

int main(int argc, char **argv)
{
    INPUT inputs[ACCEPTANCE_INPUTS];
    HMODULE bridge;
    UINT result;
    DWORD error;

    if (argc != 2) {
        fprintf(stderr, "usage: uu-keyboard-probe.exe BRIDGE_DLL\n");
        return 2;
    }
    bridge = LoadLibraryA(argv[1]);
    if (bridge == NULL) {
        fprintf(stderr, "LoadLibrary failed: %lu\n",
                (unsigned long)GetLastError());
        return 1;
    }
    Sleep(500);

    ZeroMemory(inputs, sizeof(inputs));
    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wVk = VK_LSHIFT;
    inputs[1].type = INPUT_KEYBOARD;
    inputs[1].ki.wVk = 'A';
    inputs[2] = inputs[1];
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP;
    inputs[3] = inputs[0];
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP;
    inputs[4].type = INPUT_KEYBOARD;
    inputs[4].ki.wVk = VK_LEFT;
    inputs[4].ki.dwFlags = KEYEVENTF_EXTENDEDKEY;
    inputs[5] = inputs[4];
    inputs[5].ki.dwFlags |= KEYEVENTF_KEYUP;

    SetLastError(ERROR_SUCCESS);
    result = SendInput(ACCEPTANCE_INPUTS, inputs, sizeof(INPUT));
    error = GetLastError();
    printf("requested=%u result=%u error=%lu\n", ACCEPTANCE_INPUTS, result,
           (unsigned long)error);
    FreeLibrary(bridge);
    return result == ACCEPTANCE_INPUTS && error == ERROR_SUCCESS ? 0 : 1;
}
