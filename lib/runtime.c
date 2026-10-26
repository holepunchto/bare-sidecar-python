#include <assert.h>
#include <bare.h>
#include <js.h>
#include <rlimit.h>
#include <signal.h>
#include <stdlib.h>
#include <uv.h>

#ifdef _WIN32
#include <io.h>
#include <windows.h>
#else
#include <unistd.h>
#endif

#include "runtime.bundle.h"

static uv_barrier_t bare__platform_ready;
static uv_async_t bare__platform_shutdown;
static js_platform_t *bare__platform;

static void
bare__on_platform_shutdown(uv_async_t *handle) {
  uv_close((uv_handle_t *) handle, NULL);
}

static void
bare__on_platform_thread(void *data) {
  int err;

  uv_loop_t loop;
  err = uv_loop_init(&loop);
  assert(err == 0);

  err = uv_async_init(&loop, &bare__platform_shutdown, bare__on_platform_shutdown);
  assert(err == 0);

  err = js_create_platform(&loop, NULL, &bare__platform);
  assert(err == 0);

  uv_barrier_wait(&bare__platform_ready);

  err = uv_run(&loop, UV_RUN_DEFAULT);
  assert(err == 0);

  err = js_destroy_platform(bare__platform);
  assert(err == 0);

  err = uv_run(&loop, UV_RUN_DEFAULT);
  assert(err == 0);

  err = uv_loop_close(&loop);
  assert(err == 0);
}

// The host names the descriptor of the IPC connection in the environment, or
// on Windows its handle, as it cannot place it at the descriptor `Bare.IPC` is
// opened from. The variable is removed so that processes spawned by the bundle
// don't inherit it.
static void
bare__setup_ipc(void) {
  const char *value = getenv("BARE_SIDECAR_IPC");

  if (value == NULL) return;

#ifdef _WIN32
  int fd = _open_osfhandle((intptr_t) _strtoi64(value, NULL, 10), 0);

  if (fd != 3) {
    _dup2(fd, 3);
    _close(fd);
  }

  SetEnvironmentVariableA("BARE_SIDECAR_IPC", NULL);
#else
  int fd = atoi(value);

  if (fd != 3) {
    dup2(fd, 3);
    close(fd);
  }

  unsetenv("BARE_SIDECAR_IPC");
#endif
}

int
main(int argc, char *argv[]) {
  int err;

  bare__setup_ipc();

#ifdef SIGPIPE
  signal(SIGPIPE, SIG_IGN);
#endif

  err = rlimit_set(rlimit_open_files, rlimit_infer);
  assert(err == 0);

  uv_disable_stdio_inheritance();

  argv = uv_setup_args(argc, argv);

  err = uv_barrier_init(&bare__platform_ready, 2);
  assert(err == 0);

  uv_thread_t thread;
  err = uv_thread_create(&thread, bare__on_platform_thread, NULL);
  assert(err == 0);

  uv_barrier_wait(&bare__platform_ready);

  uv_barrier_destroy(&bare__platform_ready);

  uv_loop_t *loop = uv_default_loop();

  bare_t *bare;
  err = bare_setup(loop, bare__platform, NULL, argc, (const char **) argv, NULL, &bare);
  assert(err == 0);

  uv_buf_t source = uv_buf_init((char *) runtime_bundle, runtime_bundle_len);

  err = bare_load(bare, "bare:/sidecar.bundle", &source, NULL);
  (void) err;

  err = bare_run(bare, UV_RUN_DEFAULT);
  assert(err == 0);

  int exit_code;
  err = bare_teardown(bare, UV_RUN_DEFAULT, &exit_code);
  assert(err == 0);

  err = uv_loop_close(loop);
  assert(err == 0);

  err = uv_async_send(&bare__platform_shutdown);
  assert(err == 0);

  uv_thread_join(&thread);

  return exit_code;
}
