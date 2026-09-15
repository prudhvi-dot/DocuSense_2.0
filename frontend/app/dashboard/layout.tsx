import { ReactNode } from "react";
import { Header } from "@/components/Header";

const layout = ({ children }: { children: ReactNode }) => {
  return (
      <div className="flex flex-col flex-1 h-screen">
        <Header />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
  );
};

export default layout;