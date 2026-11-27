// TASK09B. Benign-fixture-only NTFS execution prevention, .NET Framework 4.x.
// No malware, global application policy, elevation, process killing or core integration.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.CSharp;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;
using System.CodeDom.Compiler;

namespace Dacn.Task09b {
    public sealed class LabError : Exception {
        public readonly string Code;
        public LabError(string code) : base(code) { Code = code; }
    }
    public sealed class Request {
        public string request_id, case_id, target_ref, target_sha256;
        public int case_revision;
        public string action = "block_execution";
    }
    public sealed class Plan {
        public Request request;
        public string fingerprint, file_id, before_sddl, after_sddl, actor_sid, status;
    }
    public sealed class RunEvidence {
        public bool started, timed_out;
        public int native_error, exit_code;
        public string output;
    }
    public sealed class Result {
        public string request_id, operation, status, reason_code, timestamp;
        public string evaluation_type = "WINDOWS_VM_NTFS_LIVE";
        public string before_dacl_sha256, after_dacl_sha256, rollback_reference;
        public bool live_execution_verified;
        public RunEvidence execution;
    }
    public static class Codec {
        public static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        public static string Hash(byte[] bytes) {
            using (SHA256 sha = SHA256.Create()) { return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }
        }
        public static string HashText(string value) { return Hash(Encoding.UTF8.GetBytes(value)); }
        public static string Fingerprint(Request request) { return HashText(Json.Serialize(request)); }
        public static void AtomicWrite(string path, object value) {
            string temporary = path + ".new";
            byte[] bytes = Encoding.UTF8.GetBytes(Json.Serialize(value));
            using (FileStream stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None)) {
                stream.Write(bytes, 0, bytes.Length); stream.Flush(true);
            }
            if (File.Exists(path)) File.Replace(temporary, path, null);
            else File.Move(temporary, path);
        }
    }
    internal sealed class PinnedFile : IDisposable {
        [StructLayout(LayoutKind.Sequential)] internal struct Info {
            public uint attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME creation, access, write;
            public uint volume, size_high, size_low, links, index_high, index_low;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
        [DllImport("advapi32.dll")] static extern uint GetSecurityInfo(SafeFileHandle h, int type, uint info, out IntPtr owner, out IntPtr group, out IntPtr dacl, out IntPtr sacl, out IntPtr descriptor);
        [DllImport("advapi32.dll")] static extern uint SetSecurityInfo(SafeFileHandle h, int type, uint info, IntPtr owner, IntPtr group, IntPtr dacl, IntPtr sacl);
        [DllImport("advapi32.dll")] static extern uint GetSecurityDescriptorLength(IntPtr descriptor);
        [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetSecurityDescriptorDacl(IntPtr sd, out bool present, out IntPtr dacl, out bool defaulted);
        [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
        readonly FileStream stream;
        public readonly string FileId, Sha256;
        public PinnedFile(string path, bool writeDacl) {
            SafeFileHandle handle = CreateFile(path, 0x80020000U | (writeDacl ? 0x40000U : 0), 1, IntPtr.Zero, 3, 0x00200000U, IntPtr.Zero);
            if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error); }
            try {
                Info information;
                if (!GetFileInformationByHandle(handle, out information)) throw new Win32Exception(Marshal.GetLastWin32Error());
                if ((information.attributes & (0x400U | 0x10U)) != 0 || information.links != 1)
                    throw new LabError("REPARSE_DIRECTORY_OR_HARDLINK_REJECTED");
                if (information.size_high != 0 || information.size_low > 16 * 1024 * 1024)
                    throw new LabError("FIXTURE_TOO_LARGE");
                FileId = information.volume.ToString("X8") + ":" + information.index_high.ToString("X8") + information.index_low.ToString("X8");
                stream = new FileStream(handle, FileAccess.Read);
                using (SHA256 sha = SHA256.Create()) { Sha256 = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
                stream.Position = 0;
                if (stream.ReadByte() != 'M' || stream.ReadByte() != 'Z') throw new LabError("FIXTURE_NOT_PE");
            } catch { if (stream != null) stream.Dispose(); else handle.Dispose(); throw; }
        }
        public FileSecurity Acl() {
            IntPtr owner, group, dacl, sacl, descriptor;
            uint error = GetSecurityInfo(stream.SafeFileHandle, 1, 4, out owner, out group, out dacl, out sacl, out descriptor);
            if (error != 0) throw new Win32Exception((int)error);
            try {
                uint length = GetSecurityDescriptorLength(descriptor);
                if (length == 0 || length > 65536) throw new LabError("INVALID_SECURITY_DESCRIPTOR");
                byte[] bytes = new byte[length]; Marshal.Copy(descriptor, bytes, 0, bytes.Length);
                FileSecurity security = new FileSecurity();
                security.SetSecurityDescriptorBinaryForm(bytes, AccessControlSections.Access);
                return security;
            } finally { LocalFree(descriptor); }
        }
        public string Sddl() { return Acl().GetSecurityDescriptorSddlForm(AccessControlSections.Access); }
        public void SetAcl(FileSecurity security) {
            byte[] binary = security.GetSecurityDescriptorBinaryForm();
            GCHandle pinned = GCHandle.Alloc(binary, GCHandleType.Pinned);
            try {
                bool present, defaulted; IntPtr dacl;
                if (!GetSecurityDescriptorDacl(pinned.AddrOfPinnedObject(), out present, out dacl, out defaulted)
                    || !present || dacl == IntPtr.Zero) throw new LabError("NULL_DACL_FORBIDDEN");
                uint error = SetSecurityInfo(stream.SafeFileHandle, 1, 4, IntPtr.Zero, IntPtr.Zero, dacl, IntPtr.Zero);
                if (error != 0) throw new Win32Exception((int)error);
            } finally { pinned.Free(); }
        }
        public void Dispose() { stream.Dispose(); }
    }
    public sealed class LabBackend {
        public const string FixedRoot = @"C:\DACN09B-Lab\LiveRuns";
        public readonly string Root;
        readonly Func<Request,string,bool> authorize;
        readonly string sid = WindowsIdentity.GetCurrent().User.Value;
        public string FailNext; // trusted harness fault injection, never request input
        public static void GuardVm() {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new LabError("WINDOWS_REQUIRED");
            using (RegistryKey key = Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\BIOS")) {
                string product = key == null ? "" : Convert.ToString(key.GetValue("SystemProductName"));
                if (product.IndexOf("VirtualBox", StringComparison.OrdinalIgnoreCase) < 0
                    || !String.Equals(Environment.MachineName, "DACN09B-LAB", StringComparison.OrdinalIgnoreCase))
                    throw new LabError("APPROVED_LAB_VM_REQUIRED");
            }
            if (new DriveInfo(@"C:\").DriveFormat != "NTFS") throw new LabError("NTFS_REQUIRED");
        }
        public LabBackend(string root, Func<Request,string,bool> authorizer) {
            GuardVm();
            Root = Path.GetFullPath(root);
            if (!Root.StartsWith(FixedRoot + "\\", StringComparison.OrdinalIgnoreCase)
                || !Guid.TryParse(Path.GetFileName(Root), out unusedGuid)) throw new LabError("LAB_ROOT_REJECTED");
            CheckLinks(Root);
            authorize = authorizer ?? ((r, op) => false);
        }
        static Guid unusedGuid;
        static void CheckLinks(string path) {
            for (string current = path; !String.IsNullOrEmpty(current); current = Path.GetDirectoryName(current)) {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new LabError("REPARSE_POINT_REJECTED");
            }
        }
        string Target(Request request) {
            if (request == null || !Guid.TryParse(request.request_id, out unusedGuid)
                || request.case_id != "task09b-benign-lab" || request.case_revision != 1 || request.action != "block_execution")
                throw new LabError("REQUEST_BINDING_INVALID");
            if (request.target_ref != "target.exe") throw new LabError("TARGET_OUTSIDE_APPROVED_FIXTURE");
            string path = Path.Combine(Root, request.target_ref); CheckLinks(path); return path;
        }
        string PlanPath(Request request) { Target(request); return Path.Combine(Root, request.request_id + ".json"); }
        Plan Load(Request request) {
            Plan plan = Codec.Json.Deserialize<Plan>(File.ReadAllText(PlanPath(request)));
            if (plan.fingerprint != Codec.Fingerprint(request) || plan.actor_sid != sid) throw new LabError("REQUEST_OR_ACTOR_MISMATCH");
            return plan;
        }
        void Persist(Plan plan) { Codec.AtomicWrite(PlanPath(plan.request), plan); }
        void Bind(PinnedFile target, Request request, Plan plan) {
            if (!String.Equals(target.Sha256, request.target_sha256, StringComparison.Ordinal)) throw new LabError("TARGET_HASH_MISMATCH");
            if (plan != null && target.FileId != plan.file_id) throw new LabError("TARGET_FILE_ID_MISMATCH");
        }
        FileSystemAccessRule OwnedRule() {
            return new FileSystemAccessRule(new SecurityIdentifier(sid), FileSystemRights.ExecuteFile,
                                           InheritanceFlags.None, PropagationFlags.None, AccessControlType.Deny);
        }
        FileStream LockJournal() { return new FileStream(Path.Combine(Root, "operations.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
        Result Log(Request request, string operation, string status, string reason, string before, string after, RunEvidence execution) {
            Result result = new Result { request_id = request == null ? "invalid" : request.request_id,
                operation=operation, status=status, reason_code=reason, timestamp=DateTime.UtcNow.ToString("o"),
                before_dacl_sha256=before == null ? null : Codec.HashText(before),
                after_dacl_sha256=after == null ? null : Codec.HashText(after),
                rollback_reference=request == null ? null : request.request_id, execution=execution,
                live_execution_verified=status == "LIVE_BLOCK_VERIFIED" };
            byte[] line = Encoding.UTF8.GetBytes(Codec.Json.Serialize(result) + "\n");
            using (FileStream log = new FileStream(Path.Combine(Root, "audit.jsonl"), FileMode.Append, FileAccess.Write, FileShare.Read)) {
                log.Write(line, 0, line.Length); log.Flush(true);
            }
            return result;
        }
        static string Reason(Exception exception) {
            LabError lab = exception as LabError;
            Win32Exception native = exception as Win32Exception;
            return lab != null ? lab.Code : native != null ? "WIN32_" + native.NativeErrorCode : exception.GetType().Name;
        }
        Result Operate(Request request, string operation, Func<Result> body) {
            try { GuardVm(); using (FileStream gate = LockJournal()) { return body(); } }
            catch (Exception exception) {
                // If durable audit itself is unavailable, propagate instead of inventing success.
                return Log(request, operation, "REJECTED_OR_PARTIAL_REVIEW_MANIFEST", Reason(exception), null, null, null);
            }
        }
        public Result PlanBlock(Request request) {
            return Operate(request, "plan_block", () => {
                string path = Target(request);
                using (PinnedFile target = new PinnedFile(path, false)) {
                    Bind(target, request, null);
                    if (File.Exists(PlanPath(request))) { Load(request); return Log(request,"plan_block","PLANNED","DUPLICATE_PLAN",target.Sddl(),target.Sddl(),null); }
                    FileSecurity security = target.Acl();
                    foreach (FileSystemAccessRule rule in security.GetAccessRules(true, true, typeof(SecurityIdentifier)))
                        if (rule.AccessControlType == AccessControlType.Deny && rule.IdentityReference.Value == sid)
                            throw new LabError("PREEXISTING_ACTOR_DENY_REQUIRES_REVIEW");
                    string before = target.Sddl(); security.AddAccessRule(OwnedRule());
                    Plan plan = new Plan { request=request, fingerprint=Codec.Fingerprint(request), file_id=target.FileId,
                        before_sddl=before, after_sddl=security.GetSecurityDescriptorSddlForm(AccessControlSections.Access), actor_sid=sid, status="PLANNED" };
                    Persist(plan);
                    return Log(request,"plan_block","PLANNED","DRY_RUN_ACL_UNCHANGED",before,target.Sddl(),null);
                }
            });
        }
        public Result ApplyBlock(Request request) {
            return Operate(request,"apply_block", () => {
                if (!authorize(request,"apply_block")) throw new LabError("TRUSTED_HARNESS_AUTHORIZATION_DENIED");
                Plan plan = Load(request);
                using (PinnedFile target = new PinnedFile(Target(request),true)) {
                    Bind(target, request, plan);
                    if (plan.status == "APPLIED") return Log(request,"apply_block","NO_CHANGE","DUPLICATE_APPLY_USE_VERIFY",target.Sddl(),target.Sddl(),null);
                    if (plan.status != "PLANNED") throw new LabError("NEW_REQUEST_OR_RECOVERY_REQUIRED");
                    if (target.Sddl() != plan.before_sddl) throw new LabError("DACL_STATE_DRIFT");
                    plan.status="APPLY_INTENT"; Persist(plan);
                    Log(request,"apply_block","INTENT","BEFORE_FILE_DACL_CHANGE",plan.before_sddl,null,null);
                    if (FailNext == "apply") { FailNext=null; throw new LabError("INJECTED_APPLY_FAILURE"); }
                    FileSecurity security=target.Acl(); security.AddAccessRule(OwnedRule()); target.SetAcl(security);
                    string after=target.Sddl();
                    if (after != plan.after_sddl) throw new LabError("APPLY_READBACK_MISMATCH_RECOVERY_REQUIRED");
                    plan.status="APPLIED"; Persist(plan);
                    return Log(request,"apply_block","APPLIED","FILE_DACL_READBACK_MATCHES",plan.before_sddl,after,null);
                }
            });
        }
        public RunEvidence RunFixture(string name, string expectedHash, string expectedToken) {
            if (name != "target.exe" && name != "control.exe") throw new LabError("FIXTURE_NOT_ALLOWLISTED");
            using (PinnedFile pinned = new PinnedFile(Path.Combine(Root,name),false)) {
                if (pinned.Sha256 != expectedHash) throw new LabError("RUN_FIXTURE_HASH_MISMATCH");
                try {
                    ProcessStartInfo start = new ProcessStartInfo(Path.Combine(Root,name));
                    start.UseShellExecute=false; start.CreateNoWindow=true; start.RedirectStandardOutput=true;
                    using (Process process=Process.Start(start)) {
                        if (!process.WaitForExit(10000)) return new RunEvidence { started=true, timed_out=true, exit_code=-1 };
                        string output=process.StandardOutput.ReadToEnd().Trim();
                        if (output != expectedToken || process.ExitCode != 0) throw new LabError("BENIGN_FIXTURE_OUTPUT_MISMATCH");
                        return new RunEvidence { started=true, exit_code=process.ExitCode, output=output };
                    }
                } catch (Win32Exception exception) { return new RunEvidence { started=false, native_error=exception.NativeErrorCode, exit_code=-1 }; }
            }
        }
        public Result VerifyBlock(Request request, string expectedToken) {
            return Operate(request,"verify_block", () => {
                if (!authorize(request,"verify_block")) throw new LabError("TRUSTED_HARNESS_AUTHORIZATION_DENIED");
                Plan plan=Load(request);
                using (PinnedFile target=new PinnedFile(Target(request),false)) {
                    Bind(target,request,plan);
                    if (!(new string[]{"APPLIED","APPLY_INTENT","ROLLBACK_INTENT"}.Contains(plan.status))
                        || target.Sddl() != plan.after_sddl) throw new LabError("APPLIED_RULE_STATE_MISMATCH");
                }
                RunEvidence execution=RunFixture("target.exe",request.target_sha256,expectedToken);
                if (execution.started || execution.native_error != 5) throw new LabError("EXECUTION_BLOCK_NOT_PROVEN");
                return Log(request,"verify_block","LIVE_BLOCK_VERIFIED","CREATEPROCESS_ACCESS_DENIED_5",plan.before_sddl,plan.after_sddl,execution);
            });
        }
        public Result RollbackBlock(Request request) {
            return Operate(request,"rollback_block", () => {
                if (!authorize(request,"rollback_block")) throw new LabError("TRUSTED_HARNESS_AUTHORIZATION_DENIED");
                Plan plan=Load(request);
                using (PinnedFile target=new PinnedFile(Target(request),true)) {
                    Bind(target,request,plan); string current=target.Sddl();
                    if (current == plan.before_sddl && plan.status != "PLANNED") {
                        plan.status="ROLLED_BACK"; Persist(plan);
                        return Log(request,"rollback_block","ROLLED_BACK","ALREADY_BASELINE_NO_CHANGE",current,current,null);
                    }
                    if (current != plan.after_sddl) throw new LabError("ROLLBACK_DACL_DRIFT_REQUIRES_REVIEW");
                    plan.status="ROLLBACK_INTENT"; Persist(plan);
                    Log(request,"rollback_block","INTENT","BEFORE_OWNED_ACE_REMOVAL",current,null,null);
                    if (FailNext == "rollback") { FailNext=null; throw new LabError("INJECTED_ROLLBACK_FAILURE"); }
                    FileSecurity security=target.Acl(); security.RemoveAccessRuleSpecific(OwnedRule());
                    if (security.GetSecurityDescriptorSddlForm(AccessControlSections.Access) != plan.before_sddl)
                        throw new LabError("REMOVAL_WOULD_NOT_PRESERVE_BASELINE");
                    target.SetAcl(security);
                    if (target.Sddl() != plan.before_sddl) throw new LabError("ROLLBACK_READBACK_MISMATCH");
                    plan.status="ROLLED_BACK"; Persist(plan);
                    return Log(request,"rollback_block","ROLLED_BACK","OWNED_ACE_REMOVED_BASELINE_MATCHES",current,target.Sddl(),null);
                }
            });
        }
        public static string DaclDigest(string path) { using (PinnedFile target=new PinnedFile(path,false)) { return Codec.HashText(target.Sddl()); } }
    }
    public static class Program {
        static readonly List<object> checks=new List<object>();
        static void Check(string name, bool passed) { checks.Add(new { name=name, passed=passed }); if (!passed) throw new LabError("CHECK_FAILED_"+name); }
        static string BuildFixture(string root,string name,string token) {
            string source="using System; public static class HelloLab { public static int Main(){Console.WriteLine(\""+token+"\");return 0;} }";
            using (CSharpCodeProvider compiler=new CSharpCodeProvider()) {
                CompilerParameters options=new CompilerParameters(new string[] {"System.dll"},Path.Combine(root,name),false);
                options.GenerateExecutable=true; options.GenerateInMemory=false;
                CompilerResults result=compiler.CompileAssemblyFromSource(options,source);
                if (result.Errors.HasErrors) throw new LabError("BENIGN_FIXTURE_COMPILE_FAILED");
            }
            return Codec.Hash(File.ReadAllBytes(Path.Combine(root,name)));
        }
        static Request NewRequest(string hash) { return new Request { request_id=Guid.NewGuid().ToString(), case_id="task09b-benign-lab",case_revision=1,target_ref="target.exe",target_sha256=hash }; }
        static object Demo() {
            LabBackend.GuardVm();
            string proofPath=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"snapshot-proof.json");
            Dictionary<string,object> proof=Codec.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(proofPath));
            if (!proof.ContainsKey("status") || Convert.ToString(proof["status"]) != "PASS_MARKER_RESTORE_TEST"
                || Convert.ToString(proof["snapshot_uuid"]) != "a52ed8f3-1543-44fd-86d2-6d0ac2223a29")
                throw new LabError("TRUSTED_HARNESS_SNAPSHOT_RECORD_REQUIRED");
            string root=Path.Combine(LabBackend.FixedRoot,Guid.NewGuid().ToString()); Directory.CreateDirectory(root);
            string targetToken="TARGET_"+Guid.NewGuid().ToString("N"), controlToken="CONTROL_"+Guid.NewGuid().ToString("N");
            string targetHash=BuildFixture(root,"target.exe",targetToken), controlHash=BuildFixture(root,"control.exe",controlToken);
            HashSet<string> authorized=new HashSet<string>();
            Func<Request,string,bool> authorizer=(candidate,operation) => authorized.Contains(Codec.Fingerprint(candidate))
                && new string[]{"apply_block","verify_block","rollback_block"}.Contains(operation);
            LabBackend backend=new LabBackend(root,authorizer);
            Request request=NewRequest(targetHash); authorized.Add(Codec.Fingerprint(request));
            string baseline=LabBackend.DaclDigest(Path.Combine(root,"target.exe"));
            List<Result> results=new List<Result>();
            try {
                RunEvidence before=backend.RunFixture("target.exe",targetHash,targetToken);
                RunEvidence controlBefore=backend.RunFixture("control.exe",controlHash,controlToken);
                Check("target_runs_before",before.started && before.exit_code==0);
                Check("control_runs_before",controlBefore.started && controlBefore.exit_code==0);
                Result plan=backend.PlanBlock(request); results.Add(plan);
                Check("dry_run_no_dacl_change",plan.status=="PLANNED" && LabBackend.DaclDigest(Path.Combine(root,"target.exe"))==baseline);
                Request badHash=NewRequest(new string('0',64));
                Check("hash_mismatch_rejected",backend.PlanBlock(badHash).reason_code=="TARGET_HASH_MISMATCH");
                Request outside=NewRequest(targetHash); outside.target_ref="..\\outside.exe";
                Check("path_escape_rejected",backend.PlanBlock(outside).reason_code=="TARGET_OUTSIDE_APPROVED_FIXTURE");
                LabBackend denied=new LabBackend(root,null);
                Check("authorization_default_deny",denied.ApplyBlock(request).reason_code=="TRUSTED_HARNESS_AUTHORIZATION_DENIED");
                Result apply=backend.ApplyBlock(request); results.Add(apply); Check("apply_readback",apply.status=="APPLIED");
                Result verify=backend.VerifyBlock(request,targetToken); results.Add(verify);
                Check("target_createprocess_denied_5",verify.status=="LIVE_BLOCK_VERIFIED" && verify.execution.native_error==5);
                RunEvidence controlDuring=backend.RunFixture("control.exe",controlHash,controlToken);
                Check("control_runs_during_block",controlDuring.started && controlDuring.exit_code==0);
                Check("duplicate_apply_no_change",backend.ApplyBlock(request).reason_code=="DUPLICATE_APPLY_USE_VERIFY");
                Check("separate_rollback_authorization",denied.RollbackBlock(request).reason_code=="TRUSTED_HARNESS_AUTHORIZATION_DENIED");
                backend.FailNext="rollback";
                Check("rollback_failure_audited",backend.RollbackBlock(request).reason_code=="INJECTED_ROLLBACK_FAILURE");
                Check("still_blocked_after_failed_rollback",backend.VerifyBlock(request,targetToken).live_execution_verified);
                Result rollback=backend.RollbackBlock(request); results.Add(rollback);
                Check("rollback_readback",rollback.status=="ROLLED_BACK" && LabBackend.DaclDigest(Path.Combine(root,"target.exe"))==baseline);
                RunEvidence after=backend.RunFixture("target.exe",targetHash,targetToken);
                Check("target_runs_after_rollback",after.started && after.exit_code==0);
                Check("control_runs_after_rollback",backend.RunFixture("control.exe",controlHash,controlToken).started);
                Check("duplicate_rollback_no_change",backend.RollbackBlock(request).reason_code=="ALREADY_BASELINE_NO_CHANGE");
                Request failed=NewRequest(targetHash); authorized.Add(Codec.Fingerprint(failed));
                backend.PlanBlock(failed); backend.FailNext="apply";
                Check("apply_failure_audited",backend.ApplyBlock(failed).reason_code=="INJECTED_APPLY_FAILURE");
                Check("failed_apply_dacl_unchanged",LabBackend.DaclDigest(Path.Combine(root,"target.exe"))==baseline);
                Check("recover_intent_without_change",backend.RollbackBlock(failed).status=="ROLLED_BACK");
                object report=new { schema_version="task09b-ntfs-live-v1",evaluation_type="WINDOWS_VM_NTFS_LIVE",
                    status="PASS",backend="NTFS_EXECUTE_DENY_CURRENT_SID_SINGLE_FIXTURE",guest_name=Environment.MachineName,
                    timestamp=DateTime.UtcNow.ToString("o"),checks=checks,results=results,
                    before_execution=before,control_before=controlBefore,control_during=controlDuring,after_execution=after,
                    target_sha256=targetHash,control_sha256=controlHash,baseline_dacl_sha256=baseline,
                    final_dacl_sha256=LabBackend.DaclDigest(Path.Combine(root,"target.exe")),
                    snapshot_uuid=proof["snapshot_uuid"],host_policy_changes=0,global_app_policy_changes=0,
                    files_are_self_compiled_benign=true,windows_event_log_capture="NOT_ENABLED_NO_GLOBAL_AUDIT_CHANGES",
                    block_evidence="CreateProcess Win32Exception NativeErrorCode=5 plus file DACL readback; not AppLocker event 8004" };
                Codec.AtomicWrite(Path.Combine(root,"report.json"),report);
                Codec.AtomicWrite(@"C:\DACN09B-Lab\latest-report.json",report);
                return report;
            } finally {
                // Try only our own recorded ACE. On drift leave journal for explicit recovery/snapshot.
                foreach (string file in Directory.GetFiles(root,"*.json")) {
                    if (Path.GetFileName(file)=="report.json") continue;
                    try {
                        Plan saved=Codec.Json.Deserialize<Plan>(File.ReadAllText(file));
                        if (saved != null && saved.request != null && saved.status != "PLANNED" && saved.status != "ROLLED_BACK")
                            backend.RollbackBlock(saved.request);
                    } catch { /* Original failure remains visible; do not force reset an unknown ACL. */ }
                }
            }
        }
        static object Recover() {
            LabBackend.GuardVm();
            List<Result> recovered=new List<Result>();
            if (Directory.Exists(LabBackend.FixedRoot)) foreach (string root in Directory.GetDirectories(LabBackend.FixedRoot)) {
                LabBackend backend=new LabBackend(root,(request,operation) => operation=="rollback_block");
                foreach (string file in Directory.GetFiles(root,"*.json")) {
                    Guid requestId;
                    if (!Guid.TryParse(Path.GetFileNameWithoutExtension(file),out requestId)) continue;
                    Plan plan=Codec.Json.Deserialize<Plan>(File.ReadAllText(file));
                    if (plan.status!="PLANNED" && plan.status!="ROLLED_BACK") recovered.Add(backend.RollbackBlock(plan.request));
                }
            }
            bool passed=recovered.All(item => item.status=="ROLLED_BACK");
            if (!passed) throw new LabError("RECOVERY_REQUIRES_MANUAL_REVIEW_OR_SNAPSHOT");
            return new { status="RECOVERY_COMPLETE",results=recovered,global_app_policy_changes=0 };
        }
        public static int Main(string[] args) {
            try {
                if (args.Length!=1 || (args[0]!="demo" && args[0]!="capabilities" && args[0]!="recover")) throw new LabError("COMMAND_NOT_ALLOWED");
                LabBackend.GuardVm();
                if (args[0]=="capabilities") {
                    Console.WriteLine(Codec.Json.Serialize(new { status="LAB_VM_DETECTED",backend="NTFS_FILE_EXECUTE_DACL",
                        live_test="NOT_RUN_BY_THIS_COMMAND",host_policy_changes=0 }));
                } else if (args[0]=="recover") { Console.WriteLine(Codec.Json.Serialize(Recover())); }
                else {
                    object report=Demo(); Console.WriteLine(Codec.Json.Serialize(report));
                    Console.WriteLine("TASK09B LIVE NTFS: PASS ("+checks.Count+" checks); rollback verified; NO MALWARE.");
                }
                return 0;
            } catch (Exception exception) {
                LabError lab=exception as LabError;
                object failure=new { schema_version="task09b-ntfs-live-v1",evaluation_type="WINDOWS_VM_NTFS_LIVE",
                    status="FAILED_OR_BLOCKED",reason_code=lab==null?exception.GetType().Name:lab.Code,checks=checks };
                Console.WriteLine(Codec.Json.Serialize(failure));
                try { LabBackend.GuardVm(); Codec.AtomicWrite(@"C:\DACN09B-Lab\latest-failure.json",failure); } catch { }
                return 1;
            }
        }
    }
}
