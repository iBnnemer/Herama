export interface FsEntry { name: string; isDir: boolean }

export interface HeramaApi {
  backend: string;
  defaultDir(): Promise<string>;
  fsList(dir: string): Promise<FsEntry[]>;
  fsRead(file: string): Promise<string>;
  fsResolve(cwd: string, target: string): Promise<string | null>;
  fsKnowledge(dirs: string[], budget: number): Promise<{ tree: string; text: string }>;
  pickFolder(): Promise<string | null>;
  termRun(id: string, cmd: string, cwd: string): Promise<void>;
  termKill(id: string): Promise<void>;
  onTermData(cb: (m: { id: string; data: string; code?: number | null }) => void): () => void;
}

declare global {
  interface Window { herama: HeramaApi }
}
