import HeroSection from "@/components/ui/hero-01-utils/hero";
import type { NavigationSection } from "@/components/ui/hero-01-utils/header";
import Header from "@/components/ui/hero-01-utils/header";
import BrandSlider, {
  type BrandList,
} from "@/components/ui/hero-01-utils/brand-slider";
import type { AvatarList } from "@/components/ui/hero-01-utils/hero";

export default function ClinicHeroSection() {
  const navigation: NavigationSection[] = [
    {
      title: "Services",
      href: "#services",
      items: [
        {
          title: "General Consultation",
          href: "#consultation",
          description:
            "Comprehensive health checkups with AI-powered patient history recall.",
        },
        {
          title: "Digital Prescriptions",
          href: "#prescriptions",
          description:
            "Paperless prescriptions sent directly to our pharmacy counter.",
        },
        {
          title: "Pharmacy",
          href: "#pharmacy",
          description:
            "Stock-aware dispensing with automatic alternative suggestions.",
        },
        {
          title: "Patient Memory",
          href: "#memory",
          description:
            "AI remembers every visit, allergy, and treatment for seamless care.",
        },
      ],
    },
    { title: "About", href: "#about" },
    { title: "How It Works", href: "#how-it-works" },
    { title: "Contact", href: "#contact" },
  ];

  return (
    <div className="min-h-screen bg-background">
      <Header navigation={navigation} />
      <HeroSection />
      <BrandSlider />
    </div>
  );
}

export { type NavigationSection, type AvatarList, type BrandList };
