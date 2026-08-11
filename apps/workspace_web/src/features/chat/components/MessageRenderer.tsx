import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface MessageRendererProps {
  content: string;
  className?: string;
}

export function MessageRenderer({ content, className }: MessageRendererProps) {
  return (
    <div
      className={cn(
        'prose prose-sm dark:prose-invert max-w-none leading-7',
        '[&_p]:my-3 [&_p]:leading-7',
        '[&_ul]:my-3 [&_ol]:my-3 [&_li]:my-1.5 [&_li]:leading-7',
        '[&_h1]:mt-5 [&_h1]:mb-3 [&_h2]:mt-5 [&_h2]:mb-2.5 [&_h3]:mt-4 [&_h3]:mb-2',
        '[&_hr]:my-5',
        '[&_pre]:overflow-x-auto [&_pre]:my-4 [&_code]:text-xs',
        '[&_table]:my-4 [&_table]:block [&_table]:overflow-x-auto',
        '[&_blockquote]:my-4 [&_blockquote]:leading-7',
        '[&_a]:break-words',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
