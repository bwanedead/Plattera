// Windows Job Object helper to ensure that the backend sidecar process is
// terminated automatically when the app process exits. On non‑Windows
// platforms these helpers are no‑ops.

#[cfg(windows)]
mod imp {
    use std::mem::{size_of, zeroed};
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::Threading::{
        AssignProcessToJobObject, CreateJobObjectW, OpenProcess,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JobObjectExtendedLimitInformation, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        PROCESS_SET_QUOTA, PROCESS_TERMINATE,
    };

    #[derive(Debug)]
    pub struct JobHandle(HANDLE);

    impl Drop for JobHandle {
        fn drop(&mut self) {
            unsafe {
                if self.0 != 0 {
                    CloseHandle(self.0);
                }
            }
        }
    }

    /// Create a Job Object configured with KILL_ON_JOB_CLOSE so that any
    /// processes assigned to it are terminated when the job handle is closed
    /// (typically when the app process exits).
    pub fn create_kill_on_close_job() -> Option<JobHandle> {
        unsafe {
            let hjob = CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
            if hjob == 0 {
                return None;
            }

            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

            let ok = SetInformationJobObject(
                hjob,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );

            if ok == 0 {
                CloseHandle(hjob);
                None
            } else {
                Some(JobHandle(hjob))
            }
        }
    }

    /// Assign the process with the given PID to the job. If this fails we
    /// simply log via the caller; the app still has explicit shutdown logic.
    pub fn assign_pid_to_job(job: &JobHandle, pid: u32) -> bool {
        unsafe {
            let hproc = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
            if hproc == 0 {
                return false;
            }
            let ok = AssignProcessToJobObject(job.0, hproc) != 0;
            CloseHandle(hproc);
            ok
        }
    }
}

#[cfg(not(windows))]
mod imp {
    #[derive(Debug)]
    pub struct JobHandle;

    pub fn create_kill_on_close_job() -> Option<JobHandle> {
        None
    }

    pub fn assign_pid_to_job(_job: &JobHandle, _pid: u32) -> bool {
        false
    }
}

pub use imp::{assign_pid_to_job, create_kill_on_close_job, JobHandle};

