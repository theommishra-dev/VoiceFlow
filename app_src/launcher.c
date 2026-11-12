// VoiceFlow.app launcher.
//
// Starts the Python menu-bar app (voiceflow.py, using the project's .venv) as a CHILD
// process, so macOS treats VoiceFlow.app as the "responsible" app: permission prompts
// (Microphone, Accessibility, Input Monitoring) say "VoiceFlow", not Terminal or Python.
//
// The project folder is found from the app's own location: <project>/VoiceFlow.app.
// If Python crashes it is restarted (up to 5 times); a normal Quit (exit 0) ends the app.
#include <fcntl.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
static pid_t child = 0;

static void forward(int sig) { if (child > 0) kill(child, sig); }

int main(void) {
    // .../<project>/VoiceFlow.app/Contents/MacOS/VoiceFlow  ->  .../<project>
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) return 1;
    char *dir = real;
    for (int i = 0; i < 4; i++) dir = dirname(dir);

    char py[PATH_MAX], script[PATH_MAX], logp[PATH_MAX];
    snprintf(py, sizeof py, "%s/.venv/bin/python", dir);
    snprintf(script, sizeof script, "%s/voiceflow.py", dir);
    snprintf(logp, sizeof logp, "%s/voiceflow.log", dir);
    if (chdir(dir) != 0 || access(py, X_OK) != 0) {
        fprintf(stderr, "VoiceFlow: %s not found. Run ./install.sh first.\n", py);
        return 1;
    }
    signal(SIGTERM, forward);
    signal(SIGINT, forward);

    int crashes = 0;
    for (;;) {
        posix_spawn_file_actions_t fa;
        posix_spawn_file_actions_init(&fa);
        posix_spawn_file_actions_addopen(&fa, 1, logp, O_WRONLY | O_CREAT | O_APPEND, 0644);
        posix_spawn_file_actions_adddup2(&fa, 1, 2);
        char *argv[] = {py, "-u", script, NULL};
        if (posix_spawn(&child, py, &fa, NULL, argv, environ) != 0) return 1;
        posix_spawn_file_actions_destroy(&fa);
        int status = 0;
        while (waitpid(child, &status, 0) < 0) {}
        if (WIFEXITED(status) && WEXITSTATUS(status) == 0) return 0;   // user quit
        if (WIFSIGNALED(status) && (WTERMSIG(status) == SIGTERM || WTERMSIG(status) == SIGINT)) return 0;
        if (++crashes > 5) return 1;   // give up instead of looping forever
        sleep(3);
    }
}
